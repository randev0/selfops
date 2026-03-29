"""
pg_diagnostics/models.py
------------------------
Pydantic models for PostgreSQL runtime diagnostics evidence.

All models are read-only descriptions of observed database state;
none of them imply or trigger any mutation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LongIdleConnection(BaseModel):
    """A connection that has been idle longer than the configured threshold."""

    pid: int
    usename: str
    application_name: str
    state: str
    idle_duration_seconds: float
    query_truncated: str


class BlockedQuery(BaseModel):
    """A client backend that is waiting for a lock held by another session."""

    pid: int
    usename: str
    application_name: str
    query_truncated: str
    wait_event_type: Optional[str] = None
    wait_event: Optional[str] = None
    blocked_duration_seconds: float
    blocking_pids: list[int] = Field(default_factory=list)


class WaitEventSummary(BaseModel):
    """Aggregated count of connections sharing the same wait event."""

    wait_event_type: str
    wait_event: str
    count: int


class ActiveQuery(BaseModel):
    """A currently active query, truncated for safe storage."""

    pid: int
    usename: str
    application_name: str
    query_truncated: str
    duration_seconds: float
    wait_event_type: Optional[str] = None
    wait_event: Optional[str] = None


class DatabaseStats(BaseModel):
    """Selected counters from pg_stat_database for the current database."""

    numbackends: int = 0
    xact_commit: int = 0
    xact_rollback: int = 0
    blks_hit: int = 0
    blks_read: int = 0
    tup_returned: int = 0
    tup_fetched: int = 0
    deadlocks: int = 0
    conflicts: int = 0


class DatabaseDiagnostics(BaseModel):
    """
    Top-level result of a single diagnostic pass against pg_stat_activity
    and related system views.

    Stored as IncidentEvidence(evidence_type="database").
    ``available=False`` when the target database could not be reached;
    in that case all numeric fields are 0 and lists are empty.
    """

    available: bool
    error_message: Optional[str] = None
    captured_at: datetime
    database_name: Optional[str] = None

    # ---- Connection counts ----
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    idle_in_transaction_connections: int = 0
    waiting_connections: int = 0
    max_connections: Optional[int] = None
    connection_saturation_pct: Optional[float] = None

    # ---- Long-idle connections ----
    long_idle_connections: list[LongIdleConnection] = Field(default_factory=list)
    long_idle_threshold_seconds: int = 300

    # ---- Blocked queries ----
    blocked_queries: list[BlockedQuery] = Field(default_factory=list)

    # ---- Active queries (longest-running first, capped by max_rows) ----
    top_queries: list[ActiveQuery] = Field(default_factory=list)

    # ---- Connection groupings ----
    connections_by_state: dict[str, int] = Field(default_factory=dict)
    connections_by_application: dict[str, int] = Field(default_factory=dict)

    # ---- Wait events currently observed ----
    wait_events: list[WaitEventSummary] = Field(default_factory=list)

    # ---- Database-level counters ----
    db_stats: Optional[DatabaseStats] = None
