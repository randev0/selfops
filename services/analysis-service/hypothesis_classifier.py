"""
hypothesis_classifier.py
-------------------------
Deterministic rule-based classifier that produces typed Hypothesis objects
from structured evidence sources (deploy correlation, database diagnostics,
alert context) BEFORE the LLM runs.

This layer ensures the structured output always contains clearly categorized
hypotheses grounded in concrete evidence, regardless of LLM output quality.

Rules
-----
Evidence classes → hypothesis categories:

  symptom:
    - DB connection saturation >= 70%
    - Long-idle connections present (early warning even below threshold)
    - Blocked / locked queries present
    - Alert name/labels match crash-loop, OOM, high-CPU, or high-memory patterns

  trigger:
    - deploy_correlation.likely_regression = True
    - Deploys within regression window (weaker signal when not flagged as regression)

  root_cause:
    - deploy + long_idle_connections → "connection leak introduced by deploy"
    - deploy + saturation (no long_idle)  → "deploy-induced saturation, cause unclear"
    - deploy + no DB data               → "regression, cause unknown"
    - no deploy + long_idle             → "pre-existing connection leak"
    - no deploy + blocked queries       → "lock contention / misconfiguration"
    - no deploy + saturation only       → "workload increase or resource limits"
    - crash loop + no other evidence    → "application error, cause unknown"

Confidence scale
----------------
  0.6–0.9 — strong: multiple corroborating signals
  0.3–0.6 — moderate: single signal, plausible explanation
  < 0.3   — weak: speculative, insufficient evidence

Returns an empty list when no evidence supports any classification.
Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass

from domain.models import Hypothesis


# --------------------------------------------------------------------------- #
# Internal signal structs
# --------------------------------------------------------------------------- #


@dataclass
class _DeploySignals:
    available: bool = False
    likely_regression: bool = False
    regression_window_minutes: int = 0
    closest_deploy_title: str = ""
    recent_deploy_count: int = 0
    changed_files_count: int = 0


@dataclass
class _DBSignals:
    available: bool = False
    saturation_pct: float = 0.0
    total_connections: int = 0
    max_connections: int = 0
    long_idle_count: int = 0
    blocked_query_count: int = 0
    deadlock_count: int = 0
    idle_in_transaction: int = 0


# --------------------------------------------------------------------------- #
# Signal extraction
# --------------------------------------------------------------------------- #


def _extract_deploy(data: dict | None) -> _DeploySignals:
    if not data or not data.get("available"):
        return _DeploySignals()
    deploys: list = data.get("recent_deploys") or []
    files: list = data.get("changed_files_sample") or []
    closest: dict = data.get("closest_deploy") or {}
    return _DeploySignals(
        available=True,
        likely_regression=bool(data.get("likely_regression")),
        regression_window_minutes=int(data.get("regression_window_minutes") or 0),
        closest_deploy_title=str(closest.get("title") or ""),
        recent_deploy_count=len(deploys),
        changed_files_count=len(files),
    )


def _extract_db(data: dict | None) -> _DBSignals:
    if not data or not data.get("available"):
        return _DBSignals()
    try:
        sat = float(data.get("connection_saturation_pct") or 0)
    except (TypeError, ValueError):
        sat = 0.0
    long_idle: list = data.get("long_idle_connections") or []
    blocked: list = data.get("blocked_queries") or []
    db_stats: dict = data.get("db_stats") or {}
    return _DBSignals(
        available=True,
        saturation_pct=sat,
        total_connections=int(data.get("total_connections") or 0),
        max_connections=int(data.get("max_connections") or 0),
        long_idle_count=len(long_idle),
        blocked_query_count=len(blocked),
        deadlock_count=int(db_stats.get("deadlocks") or 0),
        idle_in_transaction=int(data.get("idle_in_transaction_connections") or 0),
    )


# Alert keyword sets — matched as substrings on normalised (lowercase, no-space) text
_CRASH_KW  = frozenset({"crashloop", "crashlooping", "crash", "oomkill", "oom", "restart"})
_CPU_KW    = frozenset({"highcpu", "cpuhigh", "cputhrottl", "cpuusage"})
_MEM_KW    = frozenset({"highmemory", "memoryhigh", "oomkill", "oom", "memleak"})
_LATENCY_KW = frozenset({"latency", "slow", "timeout", "responsetime", "p99", "p95"})
_ERROR_KW  = frozenset({"errorrate", "5xx", "error"})


def _alert_flags(alert_name: str, alert_labels: dict) -> dict[str, bool]:
    text = (alert_name + " " + " ".join(str(v) for v in alert_labels.values())).lower()
    text = text.replace(" ", "").replace("_", "").replace("-", "")
    return {
        "crash_loop":      any(kw in text for kw in _CRASH_KW),
        "high_cpu":        any(kw in text for kw in _CPU_KW),
        "high_memory":     any(kw in text for kw in _MEM_KW),
        "high_latency":    any(kw in text for kw in _LATENCY_KW),
        "high_error_rate": any(kw in text for kw in _ERROR_KW),
    }


# --------------------------------------------------------------------------- #
# Confidence helper
# --------------------------------------------------------------------------- #


def _conf(base: float, *extras: bool) -> float:
    """Add 0.1 per True extra-support signal, cap at 0.90."""
    return min(0.90, round(base + 0.1 * sum(1 for e in extras if e), 4))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def classify(
    alert_name: str,
    alert_labels: dict,
    deploy_correlation: dict | None = None,
    database_diagnostics: dict | None = None,
) -> list[Hypothesis]:
    """
    Produce a typed Hypothesis list from structured evidence.

    Categories:
      symptom    — observable effect (what monitoring shows)
      trigger    — recent change that preceded the symptom
      root_cause — underlying technical reason connecting trigger to symptom

    Confidence is conservative:
      0.6–0.9 for strong multi-signal correlations,
      0.3–0.6 for single-signal inferences,
      <0.3 for speculative / missing evidence.

    Always returns a plain list (may be empty). Never raises.
    """
    try:
        return _classify(alert_name, alert_labels, deploy_correlation, database_diagnostics)
    except Exception:
        return []


def _classify(
    alert_name: str,
    alert_labels: dict,
    deploy_correlation: dict | None,
    database_diagnostics: dict | None,
) -> list[Hypothesis]:
    deploy = _extract_deploy(deploy_correlation)
    db = _extract_db(database_diagnostics)
    alert = _alert_flags(alert_name, alert_labels)

    result: list[Hypothesis] = []

    # ------------------------------------------------------------------ #
    # SYMPTOMS
    # ------------------------------------------------------------------ #

    # DB connection saturation (primary observable symptom)
    if db.available and db.saturation_pct >= 70:
        result.append(Hypothesis(
            title="Database connection pool saturation",
            description=(
                f"Database connections are at {db.saturation_pct:.1f}% saturation "
                f"({db.total_connections}/{db.max_connections or '?'}). "
                "High saturation causes new connection attempts to fail or queue, "
                "producing service errors and timeouts."
            ),
            category="symptom",
            reasoning_summary=(
                f"connection_saturation_pct={db.saturation_pct:.1f}% exceeds the 70% "
                "warning threshold — directly observable in DB diagnostics."
            ),
            confidence=_conf(0.65, db.saturation_pct >= 90, db.long_idle_count > 3),
            supporting_evidence=["connection_saturation_pct", "connection_counts"]
            + (["long_idle_connections"] if db.long_idle_count > 0 else []),
            rank=1,
        ))

    # Long-idle connections below saturation threshold (early warning)
    if db.available and db.long_idle_count > 0 and db.saturation_pct < 70:
        result.append(Hypothesis(
            title="Elevated idle database connections",
            description=(
                f"{db.long_idle_count} connection(s) have been idle longer than the "
                "configured threshold. This is an early warning of a potential connection "
                "leak, even though overall saturation has not yet crossed 70%."
            ),
            category="symptom",
            reasoning_summary=(
                f"{db.long_idle_count} long-idle connection(s) in pg_stat_activity — "
                "observable symptom before saturation becomes critical."
            ),
            confidence=_conf(0.45, db.long_idle_count > 5),
            supporting_evidence=["long_idle_connections"],
            rank=1,
        ))

    # Lock contention / blocked queries
    if db.available and db.blocked_query_count > 0:
        result.append(Hypothesis(
            title="Lock contention causing query blocking",
            description=(
                f"{db.blocked_query_count} query/queries are blocked waiting for locks. "
                "This causes latency spikes and can escalate to application timeouts."
            ),
            category="symptom",
            reasoning_summary=(
                f"{db.blocked_query_count} blocked queries in pg_stat_activity — "
                "directly observable lock contention."
                + (" Deadlocks also detected." if db.deadlock_count > 0 else "")
            ),
            confidence=_conf(0.60, db.deadlock_count > 0),
            supporting_evidence=["blocked_queries"]
            + (["deadlocks"] if db.deadlock_count > 0 else []),
            rank=1,
        ))

    # Alert-based symptoms
    if alert["crash_loop"]:
        result.append(Hypothesis(
            title="Pod crash loop",
            description=(
                "The alert indicates one or more pods are crash-looping or have been "
                "repeatedly restarted. This is the primary observable symptom; the "
                "underlying cause requires further investigation."
            ),
            category="symptom",
            reasoning_summary="Alert name/labels contain crash/OOM/restart keywords — directly observable.",
            confidence=0.75,
            supporting_evidence=["alert"],
            rank=1,
        ))

    if alert["high_cpu"]:
        result.append(Hypothesis(
            title="Elevated CPU utilization",
            description=(
                "CPU usage has exceeded the configured alert threshold. Possible causes "
                "include a traffic spike, an infinite loop, or excessive query load."
            ),
            category="symptom",
            reasoning_summary="Alert name/labels indicate high CPU — directly observable metric.",
            confidence=0.70,
            supporting_evidence=["alert"],
            rank=1,
        ))

    if alert["high_memory"]:
        result.append(Hypothesis(
            title="Elevated memory consumption",
            description=(
                "Memory usage has exceeded the alert threshold. This may indicate a "
                "memory leak or an under-provisioned memory limit."
            ),
            category="symptom",
            reasoning_summary="Alert name/labels indicate high memory — directly observable metric.",
            confidence=0.70,
            supporting_evidence=["alert"],
            rank=1,
        ))

    # ------------------------------------------------------------------ #
    # TRIGGERS
    # ------------------------------------------------------------------ #

    if deploy.available and deploy.likely_regression:
        title_str = f"'{deploy.closest_deploy_title}'" if deploy.closest_deploy_title else "a deploy"
        mins = deploy.regression_window_minutes
        result.append(Hypothesis(
            title="Recent deploy preceded the incident",
            description=(
                f"Deploy {title_str} was detected {mins} minute(s) before the incident, "
                "within the regression detection window. Deploys are the most common trigger "
                "for sudden behavioral changes in production services."
            ),
            category="trigger",
            reasoning_summary=(
                f"deploy_correlation.likely_regression=True; {title_str} was {mins}m before "
                "the incident — temporal proximity is the primary signal."
            ),
            confidence=_conf(
                0.65,
                deploy.changed_files_count > 5,
                mins < 15,
            ),
            supporting_evidence=["likely_regression"]
            + (["changed_files_count"] if deploy.changed_files_count > 0 else []),
            rank=1,
        ))

    elif deploy.available and deploy.recent_deploy_count > 0:
        # Deploys exist but not flagged as likely regression
        result.append(Hypothesis(
            title="Deploy activity in correlation window (weak signal)",
            description=(
                f"{deploy.recent_deploy_count} deploy event(s) in the correlation window, "
                "but not flagged as a likely regression. May be coincidental or a slow-burn "
                "regression that has not yet been confirmed."
            ),
            category="trigger",
            reasoning_summary=(
                f"{deploy.recent_deploy_count} deploy(s) present but likely_regression=False — "
                "moderate signal; could be coincidental."
            ),
            confidence=0.30,
            supporting_evidence=["deploy_activity"],
            rank=1,
        ))

    # ------------------------------------------------------------------ #
    # ROOT CAUSES — inferred from trigger + symptom combinations
    # ------------------------------------------------------------------ #

    if deploy.likely_regression and db.available and db.long_idle_count > 0:
        # Strongest composite: deploy + long-idle → connection leak
        mins = deploy.regression_window_minutes
        result.append(Hypothesis(
            title="Connection leak introduced by recent deploy",
            description=(
                f"A deploy occurred {mins}m before the incident AND "
                f"{db.long_idle_count} long-idle database connection(s) are present. "
                "This combination strongly suggests the deploy introduced a connection leak — "
                "connections are opened but not returned to the pool. "
                "Recommended fix: rollout restart to recover connections, then audit the new "
                "code for unclosed connection handles."
            ),
            category="root_cause",
            reasoning_summary=(
                "Deploy trigger + long_idle_connections symptom both present — "
                "the deploy is the most probable source of the leak."
            ),
            confidence=_conf(
                0.65,
                db.saturation_pct >= 70,
                deploy.regression_window_minutes < 15,
                db.long_idle_count > 3,
            ),
            supporting_evidence=["likely_regression", "long_idle_connections", "connection_saturation_pct"],
            rank=1,
        ))

    elif deploy.likely_regression and db.available and db.saturation_pct >= 70:
        # Deploy + saturation but no long-idle evidence
        mins = deploy.regression_window_minutes
        result.append(Hypothesis(
            title="Deploy-induced DB saturation (mechanism unclear)",
            description=(
                f"A deploy occurred {mins}m before the incident and DB connections are at "
                f"{db.saturation_pct:.1f}% saturation, but no long-idle connections were found. "
                "The deploy may have caused a traffic spike, introduced an inefficient query, "
                "or changed connection pool configuration."
            ),
            category="root_cause",
            reasoning_summary=(
                "Deploy trigger + high connection_saturation_pct present, but no "
                "long_idle_connections — connection leak is less certain."
            ),
            confidence=_conf(0.45, deploy.regression_window_minutes < 15),
            supporting_evidence=["likely_regression", "connection_saturation_pct"],
            rank=1,
        ))

    elif deploy.likely_regression and not db.available:
        # Deploy trigger with no DB data — limited inference
        mins = deploy.regression_window_minutes
        result.append(Hypothesis(
            title="Deploy regression (root cause unknown — no DB data)",
            description=(
                f"A deploy occurred {mins}m before the incident. "
                "Database diagnostics were not available so the exact failure mechanism "
                "cannot be determined. Possible causes: code defect, misconfiguration, "
                "or resource limit too low in the new version."
            ),
            category="root_cause",
            reasoning_summary=(
                "Only deploy trigger evidence is available; without DB or other diagnostics "
                "the root cause is speculative."
            ),
            confidence=0.35,
            supporting_evidence=["likely_regression"],
            rank=1,
        ))

    elif not deploy.likely_regression and db.available and db.long_idle_count > 0:
        # Long-idle without a deploy → pre-existing leak
        result.append(Hypothesis(
            title="Pre-existing connection leak (no recent deploy)",
            description=(
                f"{db.long_idle_count} long-idle connection(s) are present without a "
                "corresponding recent deploy. The connection leak appears to be pre-existing — "
                "possibly introduced in an earlier release or triggered by a change in traffic "
                "pattern."
            ),
            category="root_cause",
            reasoning_summary=(
                "long_idle_connections present but no deploy trigger — leak predates the "
                "current observation window."
            ),
            confidence=_conf(0.45, db.long_idle_count > 5, db.saturation_pct >= 70),
            supporting_evidence=["long_idle_connections"]
            + (["connection_saturation_pct"] if db.saturation_pct >= 70 else []),
            rank=1,
        ))

    elif not deploy.likely_regression and db.available and db.blocked_query_count > 0:
        # Blocked queries without deploy → misconfiguration or logic error
        result.append(Hypothesis(
            title="Query lock contention due to misconfiguration or logic error",
            description=(
                f"{db.blocked_query_count} blocked query/queries are present without a "
                "recent deploy. This suggests either a persistent misconfiguration, a "
                "long-running transaction that is not being cleaned up, or an application "
                "logic error causing lock escalation."
            ),
            category="root_cause",
            reasoning_summary=(
                "Blocked queries present without a deploy trigger — lock contention suggests "
                "a configuration or application-logic issue rather than a regression."
            ),
            confidence=_conf(0.40, db.deadlock_count > 0),
            supporting_evidence=["blocked_queries"]
            + (["deadlocks"] if db.deadlock_count > 0 else []),
            rank=1,
        ))

    elif not deploy.likely_regression and db.available and db.saturation_pct >= 70:
        # Saturation without deploy or long-idle → workload or resource limit
        result.append(Hypothesis(
            title="DB saturation from workload growth or under-provisioned limits",
            description=(
                f"DB connections are at {db.saturation_pct:.1f}% saturation with no recent "
                "deploy and no long-idle connections. This suggests organic workload growth "
                "that has exceeded the current connection pool configuration, or that the "
                "max_connections setting is too restrictive for the current load."
            ),
            category="root_cause",
            reasoning_summary=(
                "High connection_saturation_pct without deploy or long-idle signals — workload "
                "growth or under-provisioned resource limits is the most likely explanation."
            ),
            confidence=0.40,
            supporting_evidence=["connection_saturation_pct", "connection_counts"],
            rank=1,
        ))

    elif alert["crash_loop"] and not deploy.likely_regression and not db.available:
        # Crash loop with no supporting structured evidence
        result.append(Hypothesis(
            title="Application error causing crash loop (cause unknown)",
            description=(
                "The pod is crash-looping but no deploy trigger or database diagnostics are "
                "available. Possible causes: uncaught exception, missing dependency, "
                "misconfiguration, or resource exhaustion."
            ),
            category="root_cause",
            reasoning_summary=(
                "Crash loop alert present but no structured evidence to narrow the cause — "
                "confidence is low."
            ),
            confidence=0.20,
            supporting_evidence=["alert"],
            rank=1,
        ))

    return result
