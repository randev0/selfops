"""
test_pg_diagnostics.py
-----------------------
Unit tests for the PostgreSQL diagnostics adapter.

All tests are pure in-memory — no real database connections are made.
A ``FakeConnection`` doubles asyncpg, returning canned row data and
optionally simulating errors.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from pg_diagnostics.adapter import PgDiagnosticsAdapter, _normalize, fetch_diagnostics
from pg_diagnostics.config import PgDiagnosticsConfig
from pg_diagnostics.models import DatabaseDiagnostics, DatabaseStats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 3, 1, 14, 0, 0, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _cfg(**overrides) -> PgDiagnosticsConfig:
    defaults = dict(
        pg_diagnostics_enabled=True,
        pg_diagnostics_query_timeout_seconds=10.0,
        pg_diagnostics_max_rows=50,
        pg_diagnostics_max_query_length=500,
        pg_diagnostics_long_idle_threshold_seconds=300,
    )
    defaults.update(overrides)
    return PgDiagnosticsConfig(**defaults)


def _row(**kwargs) -> dict:
    """Build a minimal pg_stat_activity row dict."""
    defaults = dict(
        pid=1234,
        usename="selfops",
        application_name="selfops-worker",
        client_addr="10.0.0.1",
        state="idle",
        wait_event_type=None,
        wait_event=None,
        query_duration_seconds=None,
        state_duration_seconds=10.0,
        query_truncated="SELECT 1",
        blocking_pids=[],
    )
    defaults.update(kwargs)
    return defaults


def _db_stats_row() -> dict:
    return dict(
        numbackends=5,
        xact_commit=10000,
        xact_rollback=20,
        blks_hit=50000,
        blks_read=500,
        tup_returned=100000,
        tup_fetched=80000,
        deadlocks=0,
        conflicts=0,
    )


# ---------------------------------------------------------------------------
# FakeConnection
# ---------------------------------------------------------------------------


class _FakeRecord:
    """Mimics asyncpg.Record's dict-like interface."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()


class FakeConnection:
    """
    Test double for an asyncpg connection.

    activity_rows:     rows returned for the pg_stat_activity query
    max_conn_rows:     rows returned for the max_connections query
    db_stats_rows:     rows returned for the pg_stat_database query
    db_name_rows:      rows returned for current_database() query
    raise_on:          raise RuntimeError when this substring appears in a query
    """

    def __init__(
        self,
        activity_rows: list[dict] | None = None,
        max_conn_rows: list[dict] | None = None,
        db_stats_rows: list[dict] | None = None,
        db_name_rows: list[dict] | None = None,
        raise_on: str | None = None,
    ) -> None:
        # Use 'is not None' so that an explicitly-passed empty list is preserved
        # rather than being replaced by the default (empty list is falsy in Python).
        self._activity = activity_rows if activity_rows is not None else []
        self._max_conn = max_conn_rows if max_conn_rows is not None else [{"max_connections": 100}]
        self._db_stats = db_stats_rows if db_stats_rows is not None else [_db_stats_row()]
        self._db_name = db_name_rows if db_name_rows is not None else [{"db": "selfops"}]
        self._raise_on = raise_on
        self.executed: list[str] = []

    async def execute(self, query: str, *args) -> None:
        self.executed.append(query)

    async def fetch(self, query: str, *args) -> list[_FakeRecord]:
        if self._raise_on and self._raise_on in query:
            raise RuntimeError(f"simulated error on: {self._raise_on!r}")
        if "pg_stat_activity" in query:
            return [_FakeRecord(r) for r in self._activity]
        return []

    async def fetchrow(self, query: str, *args) -> _FakeRecord | None:
        if self._raise_on and self._raise_on in query:
            raise RuntimeError(f"simulated error on: {self._raise_on!r}")
        if "max_connections" in query:
            return _FakeRecord(self._max_conn[0]) if self._max_conn else None
        if "pg_stat_database" in query:
            return _FakeRecord(self._db_stats[0]) if self._db_stats else None
        if "current_database" in query:
            return _FakeRecord(self._db_name[0]) if self._db_name else None
        return None

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# TestNormalState
# ---------------------------------------------------------------------------


class TestNormalState:
    def test_available_true_on_success(self):
        conn = FakeConnection(activity_rows=[_row(state="idle"), _row(pid=2, state="active")])
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.available is True
        assert result.error_message is None

    def test_connection_counts(self):
        rows = [
            _row(pid=1, state="active"),
            _row(pid=2, state="idle"),
            _row(pid=3, state="idle"),
            _row(pid=4, state="idle in transaction"),
        ]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.total_connections == 4
        assert result.active_connections == 1
        assert result.idle_connections == 2
        assert result.idle_in_transaction_connections == 1

    def test_max_connections_and_saturation(self):
        rows = [_row(pid=i) for i in range(10)]
        conn = FakeConnection(activity_rows=rows, max_conn_rows=[{"max_connections": 100}])
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.max_connections == 100
        assert result.connection_saturation_pct == 10.0

    def test_database_name_populated(self):
        conn = FakeConnection(db_name_rows=[{"db": "selfops"}])
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.database_name == "selfops"

    def test_db_stats_present(self):
        conn = FakeConnection()
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.db_stats is not None
        assert result.db_stats.xact_commit == 10000

    def test_connections_by_state_grouped(self):
        rows = [
            _row(pid=1, state="active"),
            _row(pid=2, state="idle"),
            _row(pid=3, state="idle"),
        ]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.connections_by_state["active"] == 1
        assert result.connections_by_state["idle"] == 2

    def test_connections_by_application_grouped(self):
        rows = [
            _row(pid=1, application_name="worker", state="active"),
            _row(pid=2, application_name="worker", state="idle"),
            _row(pid=3, application_name="api", state="idle"),
        ]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.connections_by_application["worker"] == 2
        assert result.connections_by_application["api"] == 1

    def test_empty_activity_returns_zero_counts(self):
        conn = FakeConnection(activity_rows=[])
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.total_connections == 0
        assert result.active_connections == 0
        assert result.idle_connections == 0
        assert result.connection_saturation_pct is None


# ---------------------------------------------------------------------------
# TestHighConnectionUsage
# ---------------------------------------------------------------------------


class TestHighConnectionUsage:
    def test_saturation_pct_above_80(self):
        rows = [_row(pid=i, state="idle") for i in range(85)]
        conn = FakeConnection(
            activity_rows=rows,
            max_conn_rows=[{"max_connections": 100}],
        )
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.total_connections == 85
        assert result.connection_saturation_pct == 85.0

    def test_saturation_at_100_percent(self):
        rows = [_row(pid=i, state="active") for i in range(100)]
        conn = FakeConnection(
            activity_rows=rows,
            max_conn_rows=[{"max_connections": 100}],
        )
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.connection_saturation_pct == 100.0

    def test_saturation_none_when_max_connections_missing(self):
        rows = [_row(pid=i) for i in range(10)]
        conn = FakeConnection(activity_rows=rows, max_conn_rows=[])
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.max_connections is None
        assert result.connection_saturation_pct is None


# ---------------------------------------------------------------------------
# TestLongIdleConnections
# ---------------------------------------------------------------------------


class TestLongIdleConnections:
    def test_idle_connection_above_threshold_detected(self):
        rows = [
            _row(pid=1, state="idle", state_duration_seconds=400.0),  # > 300
            _row(pid=2, state="idle", state_duration_seconds=100.0),  # < 300
        ]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert len(result.long_idle_connections) == 1
        assert result.long_idle_connections[0].pid == 1
        assert result.long_idle_connections[0].idle_duration_seconds == 400.0

    def test_active_connection_not_in_long_idle(self):
        rows = [_row(pid=1, state="active", state_duration_seconds=9999.0)]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.long_idle_connections == []

    def test_custom_threshold_respected(self):
        rows = [
            _row(pid=1, state="idle", state_duration_seconds=120.0),
            _row(pid=2, state="idle", state_duration_seconds=60.0),
        ]
        conn = FakeConnection(activity_rows=rows)
        cfg = _cfg(pg_diagnostics_long_idle_threshold_seconds=100)
        result = _run(fetch_diagnostics(config=cfg, _conn=conn))
        assert len(result.long_idle_connections) == 1
        assert result.long_idle_connections[0].pid == 1

    def test_exactly_at_threshold_included(self):
        rows = [_row(pid=1, state="idle", state_duration_seconds=300.0)]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert len(result.long_idle_connections) == 1

    def test_long_idle_threshold_stored_in_result(self):
        conn = FakeConnection(activity_rows=[])
        result = _run(fetch_diagnostics(config=_cfg(pg_diagnostics_long_idle_threshold_seconds=600), _conn=conn))
        assert result.long_idle_threshold_seconds == 600


# ---------------------------------------------------------------------------
# TestBlockedQueries
# ---------------------------------------------------------------------------


class TestBlockedQueries:
    def test_blocked_query_detected(self):
        rows = [
            _row(pid=5, state="active", blocking_pids=[3], query_duration_seconds=12.0),
            _row(pid=3, state="active", blocking_pids=[]),
        ]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert len(result.blocked_queries) == 1
        assert result.blocked_queries[0].pid == 5
        assert result.blocked_queries[0].blocking_pids == [3]
        assert result.blocked_queries[0].blocked_duration_seconds == 12.0

    def test_non_blocked_query_not_in_blocked_list(self):
        rows = [_row(pid=1, state="active", blocking_pids=[])]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.blocked_queries == []

    def test_waiting_connections_count(self):
        rows = [
            _row(pid=1, blocking_pids=[10]),
            _row(pid=2, blocking_pids=[10]),
            _row(pid=3, blocking_pids=[]),
        ]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.waiting_connections == 2

    def test_multiple_blocking_pids_stored(self):
        rows = [_row(pid=7, blocking_pids=[1, 2, 3], query_duration_seconds=5.0)]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.blocked_queries[0].blocking_pids == [1, 2, 3]

    def test_wait_event_captured_on_blocked_query(self):
        rows = [
            _row(
                pid=5,
                state="active",
                blocking_pids=[3],
                wait_event_type="Lock",
                wait_event="relation",
                query_duration_seconds=5.0,
            )
        ]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        bq = result.blocked_queries[0]
        assert bq.wait_event_type == "Lock"
        assert bq.wait_event == "relation"


# ---------------------------------------------------------------------------
# TestWaitEvents
# ---------------------------------------------------------------------------


class TestWaitEvents:
    def test_wait_events_aggregated(self):
        rows = [
            _row(pid=1, wait_event_type="Lock", wait_event="relation"),
            _row(pid=2, wait_event_type="Lock", wait_event="relation"),
            _row(pid=3, wait_event_type="IO", wait_event="DataFileRead"),
        ]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        we = {(w.wait_event_type, w.wait_event): w.count for w in result.wait_events}
        assert we[("Lock", "relation")] == 2
        assert we[("IO", "DataFileRead")] == 1

    def test_null_wait_event_not_counted(self):
        rows = [_row(pid=1, wait_event_type=None, wait_event=None)]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.wait_events == []


# ---------------------------------------------------------------------------
# TestTopQueries
# ---------------------------------------------------------------------------


class TestTopQueries:
    def test_only_active_queries_in_top_queries(self):
        rows = [
            _row(pid=1, state="active", query_duration_seconds=5.0),
            _row(pid=2, state="idle", query_duration_seconds=100.0),
        ]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert len(result.top_queries) == 1
        assert result.top_queries[0].pid == 1

    def test_query_text_is_truncated_to_config_length(self):
        long_q = "SELECT " + "x" * 600
        rows = [_row(pid=1, state="active", query_truncated=long_q[:500])]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(pg_diagnostics_max_query_length=500), _conn=conn))
        assert len(result.top_queries[0].query_truncated) <= 500


# ---------------------------------------------------------------------------
# TestDBUnavailable
# ---------------------------------------------------------------------------


class TestDBUnavailable:
    def test_no_dsn_returns_unavailable(self):
        # Temporarily remove DATABASE_URL so effective_dsn returns None.
        # The production env always sets DATABASE_URL, so we must scrub it here
        # to test the "nothing configured" code path in isolation.
        import os
        saved = os.environ.pop("DATABASE_URL", None)
        try:
            cfg = PgDiagnosticsConfig(pg_diagnostics_dsn="", pg_diagnostics_enabled=True)
            result = _run(fetch_diagnostics(config=cfg))
            assert result.available is False
            assert result.error_message is not None
        finally:
            if saved is not None:
                os.environ["DATABASE_URL"] = saved

    def test_connection_error_returns_unavailable(self):
        conn = FakeConnection(raise_on="pg_stat_activity")
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.available is False
        assert result.error_message is not None

    def test_disabled_returns_unavailable(self):
        result = _run(fetch_diagnostics(config=_cfg(pg_diagnostics_enabled=False)))
        assert result.available is False
        assert "disabled" in (result.error_message or "").lower()

    def test_unavailable_result_has_zero_counts(self):
        conn = FakeConnection(raise_on="pg_stat_activity")
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.total_connections == 0
        assert result.blocked_queries == []
        assert result.long_idle_connections == []


# ---------------------------------------------------------------------------
# TestMalformedResponse
# ---------------------------------------------------------------------------


class TestMalformedResponse:
    def test_none_values_in_row_handled_gracefully(self):
        rows = [
            dict(
                pid=None,
                usename=None,
                application_name=None,
                client_addr=None,
                state=None,
                wait_event_type=None,
                wait_event=None,
                query_duration_seconds=None,
                state_duration_seconds=None,
                query_truncated=None,
                blocking_pids=None,
            )
        ]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.available is True
        assert result.total_connections == 1

    def test_missing_db_stats_row_returns_none(self):
        conn = FakeConnection(db_stats_rows=[])
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.db_stats is None

    def test_missing_max_connections_row(self):
        conn = FakeConnection(max_conn_rows=[])
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.max_connections is None
        assert result.connection_saturation_pct is None

    def test_non_integer_blocking_pids_treated_as_empty(self):
        rows = [_row(pid=1, blocking_pids="not-a-list")]
        conn = FakeConnection(activity_rows=rows)
        result = _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        assert result.waiting_connections == 0


# ---------------------------------------------------------------------------
# TestReadOnlySafety
# ---------------------------------------------------------------------------


class TestReadOnlySafety:
    def test_read_only_statement_issued(self):
        conn = FakeConnection()
        _run(fetch_diagnostics(config=_cfg(), _conn=conn))
        executed_upper = " ".join(conn.executed).upper()
        assert "READ ONLY" in executed_upper

    def test_statement_timeout_issued(self):
        conn = FakeConnection()
        _run(fetch_diagnostics(config=_cfg(pg_diagnostics_query_timeout_seconds=5.0), _conn=conn))
        executed = " ".join(conn.executed)
        assert "statement_timeout" in executed.lower()
        assert "5000" in executed  # 5s → 5000ms


# ---------------------------------------------------------------------------
# TestConfig
# ---------------------------------------------------------------------------


class TestConfig:
    def test_timeout_clamped_at_minimum(self):
        cfg = PgDiagnosticsConfig(pg_diagnostics_query_timeout_seconds=0.001)
        assert cfg.pg_diagnostics_query_timeout_seconds == 1.0

    def test_timeout_clamped_at_maximum(self):
        cfg = PgDiagnosticsConfig(pg_diagnostics_query_timeout_seconds=9999)
        assert cfg.pg_diagnostics_query_timeout_seconds == 60.0

    def test_max_rows_clamped_at_minimum(self):
        cfg = PgDiagnosticsConfig(pg_diagnostics_max_rows=0)
        assert cfg.pg_diagnostics_max_rows == 1

    def test_max_rows_clamped_at_maximum(self):
        cfg = PgDiagnosticsConfig(pg_diagnostics_max_rows=99999)
        assert cfg.pg_diagnostics_max_rows == 500

    def test_max_query_length_clamped(self):
        cfg = PgDiagnosticsConfig(pg_diagnostics_max_query_length=10)
        assert cfg.pg_diagnostics_max_query_length == 50

    def test_explicit_dsn_takes_priority(self):
        cfg = PgDiagnosticsConfig(pg_diagnostics_dsn="postgresql://user:pw@host/db")
        assert cfg.effective_dsn == "postgresql://user:pw@host/db"

    def test_statement_timeout_ms_calculated(self):
        cfg = PgDiagnosticsConfig(pg_diagnostics_query_timeout_seconds=7.0)
        assert cfg.statement_timeout_ms == 7000

    def test_disabled_flag(self):
        cfg = PgDiagnosticsConfig(pg_diagnostics_enabled=False)
        assert cfg.pg_diagnostics_enabled is False


# ---------------------------------------------------------------------------
# TestNormalizePure
# ---------------------------------------------------------------------------


class TestNormalizePure:
    """Tests for _normalize() as a pure function."""

    def _call(self, activity_rows, **kwargs):
        from pg_diagnostics.adapter import _normalize

        defaults = dict(
            activity_rows=activity_rows,
            max_connections=100,
            db_stats=None,
            db_name="testdb",
            captured_at=_NOW,
            config=_cfg(),
        )
        defaults.update(kwargs)
        return _normalize(**defaults)

    def test_saturation_computed_correctly(self):
        rows = [_row(pid=i) for i in range(20)]
        result = self._call(rows, max_connections=100)
        assert result.connection_saturation_pct == 20.0

    def test_long_idle_uses_state_duration_not_query_duration(self):
        # query_duration_seconds is None (idle); state_duration_seconds is large
        row = _row(state="idle", state_duration_seconds=500.0, query_duration_seconds=None)
        result = self._call([row])
        assert len(result.long_idle_connections) == 1

    def test_result_is_always_available_true(self):
        result = self._call([])
        assert result.available is True

    def test_wait_events_sorted_by_count_descending(self):
        rows = [
            _row(pid=i, wait_event_type="IO", wait_event="DataFileRead")
            for i in range(5)
        ] + [
            _row(pid=10 + i, wait_event_type="Lock", wait_event="relation")
            for i in range(2)
        ]
        result = self._call(rows)
        assert result.wait_events[0].count == 5
        assert result.wait_events[1].count == 2
