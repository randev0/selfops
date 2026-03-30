"""
evidence_summarizer.py
-----------------------
Converts raw deploy-correlation and database-diagnostics evidence dicts into:

  1. A human-readable text block for injection into the LLM prompt.
  2. A list of typed EvidenceItem objects for pre-population of
     StructuredAnalysis.evidence before the LLM output is merged in.

Both functions are pure (no I/O) and never raise — they return empty
defaults when the input is absent or malformed.
"""
from __future__ import annotations

from typing import Any

from domain.models import EvidenceItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _str(v: Any, default: str = "") -> str:
    return str(v) if v is not None else default


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


# ---------------------------------------------------------------------------
# Deploy correlation
# ---------------------------------------------------------------------------


def summarize_deploy_correlation(
    data: dict | None,
) -> tuple[str, list[EvidenceItem]]:
    """
    Convert a ChangeContext JSON dict into a prompt text block and a list of
    EvidenceItem objects.

    Returns ("", []) when data is absent or available=false.
    """
    if not data or not data.get("available"):
        return "", []

    lines: list[str] = ["DEPLOY CORRELATION:"]
    items: list[EvidenceItem] = []

    repo = _str(data.get("repo"), "(unknown repo)")
    lines.append(f"  Repository: {repo}")

    # Recent deploys
    deploys: list[dict] = data.get("recent_deploys") or []
    if deploys:
        lines.append(f"  Recent deploys in window: {len(deploys)}")
        for d in deploys[:3]:
            kind = _str(d.get("kind"), "deploy")
            ts = _str(d.get("timestamp"), "unknown time")
            title = _str(d.get("title"), "untitled")
            author = _str(d.get("author"), "unknown")
            lines.append(f"    • [{kind}] {title} by {author} at {ts}")
            items.append(
                EvidenceItem(
                    source="deploy",
                    kind="metric",
                    label=f"deploy_{_str(d.get('id', 'unknown'))[:28]}",
                    value=f"{kind}: {title} at {ts}"[:500],
                )
            )
    else:
        lines.append("  No deploys detected in the correlation window")

    # Regression flag — the most important signal
    if data.get("likely_regression"):
        minutes = _int(data.get("regression_window_minutes"), 0)
        closest = data.get("closest_deploy") or {}
        closest_title = _str(closest.get("title"), "unknown deploy")
        lines.append(
            f"  ⚠ LIKELY REGRESSION: '{closest_title}' deployed {minutes} min before incident"
        )
        items.append(
            EvidenceItem(
                source="deploy",
                kind="alert",
                label="likely_regression",
                value=(
                    f"Deploy '{closest_title}' occurred {minutes}m before incident "
                    f"(within regression threshold)"
                )[:500],
            )
        )

    # Changed files sample
    files: list[dict] = data.get("changed_files_sample") or []
    if files:
        lines.append(f"  Changed files sample ({len(files)} files):")
        for f in files[:5]:
            status = _str(f.get("status"), "modified")
            fname = _str(f.get("filename"), "unknown")
            adds = _int(f.get("additions"))
            dels = _int(f.get("deletions"))
            lines.append(f"    {status}: {fname} (+{adds}/-{dels})")
        items.append(
            EvidenceItem(
                source="deploy",
                kind="metric",
                label="changed_files_count",
                value=f"{len(files)} files changed in the deploy window",
            )
        )

    # Commit and PR counts
    total_commits = _int(data.get("total_commits"))
    total_prs = _int(data.get("total_prs_merged"))
    if total_commits or total_prs:
        lines.append(
            f"  Activity in window: {total_commits} commits, {total_prs} PRs merged"
        )
        items.append(
            EvidenceItem(
                source="deploy",
                kind="metric",
                label="deploy_activity",
                value=f"{total_commits} commits, {total_prs} PRs merged in correlation window",
            )
        )

    return "\n".join(lines), items


# ---------------------------------------------------------------------------
# Database diagnostics
# ---------------------------------------------------------------------------


def summarize_database_diagnostics(
    data: dict | None,
) -> tuple[str, list[EvidenceItem]]:
    """
    Convert a DatabaseDiagnostics JSON dict into a prompt text block and a
    list of EvidenceItem objects.

    Returns ("", []) when data is absent or available=false.
    """
    if not data or not data.get("available"):
        return "", []

    lines: list[str] = ["DATABASE DIAGNOSTICS:"]
    items: list[EvidenceItem] = []

    db_name = _str(data.get("database_name"), "unknown")
    lines.append(f"  Database: {db_name}")

    # Connection counts and saturation
    total = _int(data.get("total_connections"))
    active = _int(data.get("active_connections"))
    idle = _int(data.get("idle_connections"))
    idle_txn = _int(data.get("idle_in_transaction_connections"))
    max_conn = data.get("max_connections")
    saturation = data.get("connection_saturation_pct")

    if max_conn is not None:
        saturation_val = _float(saturation)
        lines.append(
            f"  Connections: {total}/{max_conn} ({saturation_val:.1f}% saturation)"
        )
        lines.append(
            f"    active={active}, idle={idle}, idle-in-txn={idle_txn}"
        )
        items.append(
            EvidenceItem(
                source="database",
                kind="metric",
                label="connection_saturation_pct",
                value=f"{saturation_val:.1f}% ({total}/{max_conn} connections used)",
            )
        )
    else:
        lines.append(f"  Connections: {total} (max_connections unknown)")
        lines.append(f"    active={active}, idle={idle}, idle-in-txn={idle_txn}")

    items.append(
        EvidenceItem(
            source="database",
            kind="metric",
            label="connection_counts",
            value=f"total={total} active={active} idle={idle} idle_in_txn={idle_txn}",
        )
    )

    # Long-idle connections — key indicator of a connection leak
    long_idle: list[dict] = data.get("long_idle_connections") or []
    threshold = _int(data.get("long_idle_threshold_seconds"), 300)
    if long_idle:
        lines.append(
            f"  Long-idle connections (idle >{threshold}s): {len(long_idle)}"
        )
        for conn in long_idle[:3]:
            dur = _float(conn.get("idle_duration_seconds"))
            app = _str(conn.get("application_name"), "unknown")
            user = _str(conn.get("usename"), "unknown")
            lines.append(f"    pid={conn.get('pid')} {user}@{app} idle {dur:.0f}s")
        items.append(
            EvidenceItem(
                source="database",
                kind="metric",
                label="long_idle_connections",
                value=f"{len(long_idle)} connections idle >{threshold}s (possible leak)",
            )
        )

    # Blocked queries — sign of lock contention
    blocked: list[dict] = data.get("blocked_queries") or []
    if blocked:
        lines.append(f"  Blocked queries: {len(blocked)}")
        for bq in blocked[:3]:
            dur = _float(bq.get("blocked_duration_seconds"))
            qtext = _str(bq.get("query_truncated"), "?")[:60]
            lines.append(
                f"    pid={bq.get('pid')} blocked {dur:.1f}s by {bq.get('blocking_pids')}: {qtext}..."
            )
        items.append(
            EvidenceItem(
                source="database",
                kind="alert",
                label="blocked_queries",
                value=f"{len(blocked)} queries blocked by lock contention",
            )
        )

    # Wait events — aggregated
    wait_events: list[dict] = data.get("wait_events") or []
    if wait_events:
        top = wait_events[0]
        wt = _str(top.get("wait_event_type"), "?")
        we = _str(top.get("wait_event"), "?")
        cnt = _int(top.get("count"))
        lines.append(f"  Top wait event: {wt}:{we} ({cnt} connections)")
        items.append(
            EvidenceItem(
                source="database",
                kind="metric",
                label="top_wait_event",
                value=f"{wt}:{we} affecting {cnt} connections",
            )
        )

    # DB-level stats (deadlocks, rollbacks)
    db_stats: dict = data.get("db_stats") or {}
    deadlocks = _int(db_stats.get("deadlocks"))
    rollbacks = _int(db_stats.get("xact_rollback"))
    if deadlocks > 0:
        lines.append(f"  Deadlocks detected: {deadlocks}")
        items.append(
            EvidenceItem(
                source="database",
                kind="alert",
                label="deadlocks",
                value=f"{deadlocks} deadlock(s) detected in pg_stat_database",
            )
        )
    if rollbacks > 0:
        lines.append(f"  Transaction rollbacks: {rollbacks}")
        items.append(
            EvidenceItem(
                source="database",
                kind="metric",
                label="xact_rollback",
                value=f"{rollbacks} transaction rollbacks",
            )
        )

    return "\n".join(lines), items
