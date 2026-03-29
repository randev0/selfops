"""
pg_diagnostics/adapter.py
--------------------------
Read-only PostgreSQL diagnostics adapter.

Queries pg_stat_activity and related system views to produce a
DatabaseDiagnostics snapshot.  All queries are read-only and run
within a read-only transaction.  A configurable statement_timeout
prevents runaway queries.

Entry point: ``fetch_diagnostics(config, _conn=None) -> DatabaseDiagnostics``

The optional ``_conn`` parameter accepts a pre-built connection (or
test double) so that unit tests never need a real database.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from pg_diagnostics.config import PgDiagnosticsConfig
from pg_diagnostics.models import (
    ActiveQuery,
    BlockedQuery,
    DatabaseDiagnostics,
    DatabaseStats,
    LongIdleConnection,
    WaitEventSummary,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

# Main diagnostic query against pg_stat_activity.
# Parameters: $1 = max query length (int), $2 = max rows (int)
_ACTIVITY_SQL = """
SELECT
    pid,
    COALESCE(usename, '')            AS usename,
    COALESCE(application_name, '')   AS application_name,
    COALESCE(client_addr::text, '')  AS client_addr,
    COALESCE(state, 'unknown')       AS state,
    wait_event_type,
    wait_event,
    EXTRACT(EPOCH FROM (now() - query_start))::float
                                     AS query_duration_seconds,
    EXTRACT(EPOCH FROM (now() - state_change))::float
                                     AS state_duration_seconds,
    LEFT(COALESCE(query, ''), $1)    AS query_truncated,
    COALESCE(pg_blocking_pids(pid), ARRAY[]::int[])
                                     AS blocking_pids
FROM pg_stat_activity
WHERE pid != pg_backend_pid()
  AND backend_type = 'client backend'
ORDER BY query_duration_seconds DESC NULLS LAST
LIMIT $2
"""

_MAX_CONNECTIONS_SQL = """
SELECT setting::int AS max_connections
FROM pg_settings
WHERE name = 'max_connections'
"""

_DB_STATS_SQL = """
SELECT
    numbackends,
    xact_commit,
    xact_rollback,
    blks_hit,
    blks_read,
    tup_returned,
    tup_fetched,
    deadlocks,
    conflicts
FROM pg_stat_database
WHERE datname = current_database()
"""

_CURRENT_DB_SQL = "SELECT current_database() AS db"

# ---------------------------------------------------------------------------
# Row parsing helpers
# ---------------------------------------------------------------------------


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _str(v: Any, default: str = "") -> str:
    return str(v) if v is not None else default


def _list_int(v: Any) -> list[int]:
    if not v:
        return []
    try:
        return [int(x) for x in v]
    except (TypeError, ValueError):
        return []


# ---------------------------------------------------------------------------
# Adapter class
# ---------------------------------------------------------------------------


class PgDiagnosticsAdapter:
    """
    Runs all diagnostic queries against a given asyncpg connection.

    The connection is NOT closed by this class — lifecycle is managed
    by the caller (``fetch_diagnostics``).
    """

    def __init__(self, conn: Any, config: PgDiagnosticsConfig) -> None:
        self._conn = conn
        self._cfg = config

    async def _setup(self) -> None:
        """
        Apply read-only mode and statement timeout for this session.

        Belt-and-suspenders:
          - SET SESSION CHARACTERISTICS … READ ONLY  → rejects any accidental writes
          - SET statement_timeout                    → caps runaway queries
        """
        await self._conn.execute(
            "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
        )
        await self._conn.execute(
            f"SET statement_timeout = '{self._cfg.statement_timeout_ms}ms'"
        )

    async def _fetch_activity(self) -> list[dict]:
        rows = await self._conn.fetch(
            _ACTIVITY_SQL,
            self._cfg.pg_diagnostics_max_query_length,
            self._cfg.pg_diagnostics_max_rows,
        )
        return [dict(r) for r in rows]

    async def _fetch_max_connections(self) -> Optional[int]:
        row = await self._conn.fetchrow(_MAX_CONNECTIONS_SQL)
        if row is None:
            return None
        return _int(row["max_connections"]) or None

    async def _fetch_db_stats(self) -> Optional[DatabaseStats]:
        row = await self._conn.fetchrow(_DB_STATS_SQL)
        if row is None:
            return None
        try:
            return DatabaseStats(
                numbackends=_int(row["numbackends"]),
                xact_commit=_int(row["xact_commit"]),
                xact_rollback=_int(row["xact_rollback"]),
                blks_hit=_int(row["blks_hit"]),
                blks_read=_int(row["blks_read"]),
                tup_returned=_int(row["tup_returned"]),
                tup_fetched=_int(row["tup_fetched"]),
                deadlocks=_int(row["deadlocks"]),
                conflicts=_int(row["conflicts"]),
            )
        except Exception as exc:
            log.debug("pg_diagnostics: could not parse db_stats: %s", exc)
            return None

    async def _fetch_db_name(self) -> Optional[str]:
        row = await self._conn.fetchrow(_CURRENT_DB_SQL)
        return _str(row["db"]) if row else None

    async def collect(self) -> DatabaseDiagnostics:
        """Run all queries and return a DatabaseDiagnostics snapshot."""
        captured_at = datetime.now(timezone.utc)

        await self._setup()

        activity_rows = await self._fetch_activity()
        max_connections = await self._fetch_max_connections()
        db_stats = await self._fetch_db_stats()
        db_name = await self._fetch_db_name()

        return _normalize(
            activity_rows=activity_rows,
            max_connections=max_connections,
            db_stats=db_stats,
            db_name=db_name,
            captured_at=captured_at,
            config=self._cfg,
        )


# ---------------------------------------------------------------------------
# Normalization (pure)
# ---------------------------------------------------------------------------


def _normalize(
    *,
    activity_rows: list[dict],
    max_connections: Optional[int],
    db_stats: Optional[DatabaseStats],
    db_name: Optional[str],
    captured_at: datetime,
    config: PgDiagnosticsConfig,
) -> DatabaseDiagnostics:
    """
    Pure function: convert raw pg_stat_activity rows into a
    DatabaseDiagnostics object.
    """
    total = len(activity_rows)
    active = sum(1 for r in activity_rows if r.get("state") == "active")
    idle = sum(1 for r in activity_rows if r.get("state") == "idle")
    idle_in_txn = sum(
        1
        for r in activity_rows
        if r.get("state") in ("idle in transaction", "idle in transaction (aborted)")
    )
    waiting = sum(
        1 for r in activity_rows if _list_int(r.get("blocking_pids"))
    )

    # Connection saturation
    saturation_pct: Optional[float] = None
    if max_connections and total > 0:
        saturation_pct = round((total / max_connections) * 100, 1)

    # Long-idle connections
    threshold = config.pg_diagnostics_long_idle_threshold_seconds
    long_idle: list[LongIdleConnection] = []
    for r in activity_rows:
        if r.get("state") != "idle":
            continue
        dur = _float(r.get("state_duration_seconds"))
        if dur >= threshold:
            long_idle.append(
                LongIdleConnection(
                    pid=_int(r.get("pid")),
                    usename=_str(r.get("usename")),
                    application_name=_str(r.get("application_name")),
                    state=_str(r.get("state"), "idle"),
                    idle_duration_seconds=round(dur, 1),
                    query_truncated=_str(r.get("query_truncated")),
                )
            )

    # Blocked queries
    blocked: list[BlockedQuery] = []
    for r in activity_rows:
        bpids = _list_int(r.get("blocking_pids"))
        if not bpids:
            continue
        blocked.append(
            BlockedQuery(
                pid=_int(r.get("pid")),
                usename=_str(r.get("usename")),
                application_name=_str(r.get("application_name")),
                query_truncated=_str(r.get("query_truncated")),
                wait_event_type=r.get("wait_event_type"),
                wait_event=r.get("wait_event"),
                blocked_duration_seconds=round(
                    _float(r.get("query_duration_seconds")), 1
                ),
                blocking_pids=bpids,
            )
        )

    # Top active queries (rows already sorted by duration DESC from SQL)
    top_queries: list[ActiveQuery] = []
    for r in activity_rows:
        if r.get("state") != "active":
            continue
        top_queries.append(
            ActiveQuery(
                pid=_int(r.get("pid")),
                usename=_str(r.get("usename")),
                application_name=_str(r.get("application_name")),
                query_truncated=_str(r.get("query_truncated")),
                duration_seconds=round(_float(r.get("query_duration_seconds")), 2),
                wait_event_type=r.get("wait_event_type"),
                wait_event=r.get("wait_event"),
            )
        )

    # Groupings
    state_counts: Counter = Counter()
    app_counts: Counter = Counter()
    for r in activity_rows:
        state_counts[_str(r.get("state"), "unknown")] += 1
        app_name = _str(r.get("application_name"), "(unknown)") or "(unknown)"
        app_counts[app_name] += 1

    # Wait events
    wait_counter: Counter = Counter()
    for r in activity_rows:
        wt = r.get("wait_event_type")
        we = r.get("wait_event")
        if wt and we:
            wait_counter[(wt, we)] += 1
    wait_events = [
        WaitEventSummary(wait_event_type=wt, wait_event=we, count=cnt)
        for (wt, we), cnt in wait_counter.most_common()
    ]

    return DatabaseDiagnostics(
        available=True,
        captured_at=captured_at,
        database_name=db_name,
        total_connections=total,
        active_connections=active,
        idle_connections=idle,
        idle_in_transaction_connections=idle_in_txn,
        waiting_connections=waiting,
        max_connections=max_connections,
        connection_saturation_pct=saturation_pct,
        long_idle_connections=long_idle,
        long_idle_threshold_seconds=threshold,
        blocked_queries=blocked,
        top_queries=top_queries,
        connections_by_state=dict(state_counts),
        connections_by_application=dict(app_counts),
        wait_events=wait_events,
        db_stats=db_stats,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def fetch_diagnostics(
    config: Optional[PgDiagnosticsConfig] = None,
    _conn: Any = None,
) -> DatabaseDiagnostics:
    """
    Collect PostgreSQL runtime diagnostics and return a DatabaseDiagnostics
    snapshot.

    Always returns a valid object — never raises.  When the database cannot
    be reached or diagnostics are disabled, returns
    ``DatabaseDiagnostics(available=False)``.

    Parameters
    ----------
    config:
        Config object.  Constructed from env if not provided.
    _conn:
        Pre-built asyncpg connection or test double.  When provided the
        adapter uses it directly without opening a new connection.
    """
    if config is None:
        config = PgDiagnosticsConfig()

    captured_at = datetime.now(timezone.utc)

    if not config.pg_diagnostics_enabled:
        return DatabaseDiagnostics(
            available=False,
            error_message="pg_diagnostics is disabled (PG_DIAGNOSTICS_ENABLED=false)",
            captured_at=captured_at,
        )

    # Test / injection path — use supplied connection directly
    if _conn is not None:
        try:
            adapter = PgDiagnosticsAdapter(_conn, config)
            result = await adapter.collect()
            result.captured_at = captured_at
            return result
        except Exception as exc:
            log.warning("pg_diagnostics collect failed: %s", exc)
            return DatabaseDiagnostics(
                available=False,
                error_message=str(exc),
                captured_at=captured_at,
            )

    # Production path — open a fresh asyncpg connection
    dsn = config.effective_dsn
    if not dsn:
        return DatabaseDiagnostics(
            available=False,
            error_message=(
                "No DSN configured. "
                "Set PG_DIAGNOSTICS_DSN or DATABASE_URL."
            ),
            captured_at=captured_at,
        )

    conn = None
    try:
        import asyncpg  # noqa: PLC0415

        conn = await asyncpg.connect(
            dsn,
            command_timeout=config.pg_diagnostics_query_timeout_seconds,
        )
        adapter = PgDiagnosticsAdapter(conn, config)
        result = await adapter.collect()
        result.captured_at = captured_at
        return result

    except Exception as exc:
        log.warning("pg_diagnostics.fetch_diagnostics failed: %s", exc)
        return DatabaseDiagnostics(
            available=False,
            error_message=str(exc),
            captured_at=captured_at,
        )
    finally:
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass
