"""
timeline/aggregator.py
----------------------
Merges events from all incident-related tables into a chronologically
sorted, deduplicated list of TimelineEvent objects.

Sources (computed in-memory — no extra DB table required):
  1. AlertEvent         → alert.fired / alert.resolved
  2. IncidentEvidence   → evidence.collected
  3. AnalysisResult     → analysis.completed
  4. RemediationAction  → action.requested / action.started / action.completed / action.failed
  5. AuditLog           → catch-all for events not covered by the sources above
                          (incident.created, incident.updated, gitops.pr_merged, etc.)

Deduplication is implicit: every event ID is constructed as
``<source-type>-<phase>-<db-uuid>``, which is unique by definition.
The ``seen`` set guards against any double-adds if callers pass
overlapping sequences.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from app.models import (
    AlertEvent,
    AuditLog,
    AnalysisResult,
    IncidentEvidence,
    RemediationAction,
)
from app.timeline.models import TimelineEvent


# Audit event types that are fully covered by primary-source events.
# We skip them to avoid showing the same fact twice on the timeline.
_AUDIT_SKIP = frozenset(
    {
        "action.requested",
        "action.started",
        "action.completed",
        "action.failed",
        "analysis.completed",
        "evidence.collected",
        "alert.fired",
        "alert.resolved",
    }
)

_EVIDENCE_LABEL: dict[str, str] = {
    "metric": "Metrics collected",
    "log": "Logs collected",
    "alert": "Alert evidence captured",
    "analysis_input": "Analysis input prepared",
}


def _ts(dt: datetime | None) -> datetime:
    """Return *dt* with UTC timezone, or UTC epoch when *dt* is None."""
    if dt is None:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# --------------------------------------------------------------------------- #
# Per-source converters
# --------------------------------------------------------------------------- #


def _from_alert_event(incident_id: uuid.UUID, ae: AlertEvent) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []

    annotations = ae.annotations or {}
    labels = ae.labels or {}
    description = (
        annotations.get("description")
        or annotations.get("summary")
        or f"Alertmanager fired {ae.alert_name}"
    )

    events.append(
        TimelineEvent(
            id=f"alert-fired-{ae.id}",
            incident_id=str(incident_id),
            timestamp=_ts(ae.starts_at or ae.created_at),
            event_type="alert.fired",
            source="alert",
            title=f"Alert fired: {ae.alert_name}",
            description=str(description),
            severity=labels.get("severity"),
            metadata={
                "source_id": str(ae.id),
                "alert_name": ae.alert_name,
                "labels": labels,
            },
        )
    )

    if ae.ends_at:
        events.append(
            TimelineEvent(
                id=f"alert-resolved-{ae.id}",
                incident_id=str(incident_id),
                timestamp=_ts(ae.ends_at),
                event_type="alert.resolved",
                source="alert",
                title=f"Alert resolved: {ae.alert_name}",
                description=f"Alertmanager resolved {ae.alert_name}",
                severity=labels.get("severity"),
                metadata={
                    "source_id": str(ae.id),
                    "alert_name": ae.alert_name,
                },
            )
        )

    return events


def _from_evidence(incident_id: uuid.UUID, ev: IncidentEvidence) -> TimelineEvent:
    label = _EVIDENCE_LABEL.get(ev.evidence_type, "Evidence collected")
    content = ev.content or {}
    description = content.get("description") or content.get("summary") or label
    return TimelineEvent(
        id=f"evidence-{ev.id}",
        incident_id=str(incident_id),
        timestamp=_ts(ev.captured_at),
        event_type="evidence.collected",
        source="evidence",
        title=label,
        description=str(description)[:300],
        metadata={
            "source_id": str(ev.id),
            "evidence_type": ev.evidence_type,
        },
    )


def _from_analysis(incident_id: uuid.UUID, ar: AnalysisResult) -> TimelineEvent:
    conf_pct = (
        f"{int((ar.confidence_score or 0.0) * 100)}%"
        if ar.confidence_score is not None
        else "?"
    )
    summary_text = ar.summary or "Analysis result stored"
    if ar.probable_cause:
        summary_text = f"{summary_text} — probable cause: {ar.probable_cause}"

    return TimelineEvent(
        id=f"analysis-{ar.id}",
        incident_id=str(incident_id),
        timestamp=_ts(ar.created_at),
        event_type="analysis.completed",
        source="analysis",
        title="AI analysis completed",
        description=f"[{conf_pct} confidence] {summary_text}"[:500],
        metadata={
            "source_id": str(ar.id),
            "model": ar.model_name,
            "confidence": ar.confidence_score,
            "escalate": ar.escalate,
        },
    )


def _from_action(
    incident_id: uuid.UUID, ra: RemediationAction
) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []

    # --- requested ---
    events.append(
        TimelineEvent(
            id=f"action-requested-{ra.id}",
            incident_id=str(incident_id),
            timestamp=_ts(ra.created_at),
            event_type="action.requested",
            source="action",
            title=f"Action requested: {ra.action_name}",
            description=f"{ra.action_name} requested by {ra.requested_by}",
            metadata={
                "source_id": str(ra.id),
                "action_name": ra.action_name,
                "action_type": ra.action_type,
                "requested_by": ra.requested_by,
            },
        )
    )

    # --- started ---
    if ra.started_at:
        events.append(
            TimelineEvent(
                id=f"action-started-{ra.id}",
                incident_id=str(incident_id),
                timestamp=_ts(ra.started_at),
                event_type="action.started",
                source="action",
                title=f"Action started: {ra.action_name}",
                description=f"Executing {ra.action_name}",
                metadata={"source_id": str(ra.id)},
            )
        )

    # --- completed / failed ---
    if ra.completed_at:
        status_val = ra.status.value if ra.status else ""
        success = status_val == "SUCCESS"
        phase = "completed" if success else "failed"
        fallback = f"{ra.action_name} {'succeeded' if success else 'failed'}"
        events.append(
            TimelineEvent(
                id=f"action-{phase}-{ra.id}",
                incident_id=str(incident_id),
                timestamp=_ts(ra.completed_at),
                event_type=f"action.{phase}",
                source="action",
                title=f"Action {phase}: {ra.action_name}",
                description=ra.result_summary or fallback,
                metadata={
                    "source_id": str(ra.id),
                    "status": status_val,
                    "pr_url": ra.pr_url,
                },
            )
        )

    return events


def _from_audit(incident_id: uuid.UUID, al: AuditLog) -> TimelineEvent | None:
    if al.event_type in _AUDIT_SKIP:
        return None
    return TimelineEvent(
        id=f"audit-{al.id}",
        incident_id=str(incident_id),
        timestamp=_ts(al.created_at),
        event_type=al.event_type,
        source="audit",
        title=al.message,
        description=al.message,
        metadata={
            "source_id": str(al.id),
            "actor_type": al.actor_type,
            "actor_id": al.actor_id,
        },
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def build_timeline(
    incident_id: uuid.UUID,
    alert_events: Sequence[AlertEvent],
    evidence: Sequence[IncidentEvidence],
    analysis_results: Sequence[AnalysisResult],
    remediation_actions: Sequence[RemediationAction],
    audit_logs: Sequence[AuditLog],
) -> list[TimelineEvent]:
    """
    Merge all sources into a deduplicated, chronologically sorted timeline.

    Extensibility: add new converters above and call them here.  The only
    contract is that each converter returns ``TimelineEvent`` objects whose
    ``id`` is globally unique across all sources for this incident.
    """
    raw: list[TimelineEvent] = []

    for ae in alert_events:
        try:
            raw.extend(_from_alert_event(incident_id, ae))
        except Exception:
            pass

    for ev in evidence:
        try:
            raw.append(_from_evidence(incident_id, ev))
        except Exception:
            pass

    for ar in analysis_results:
        try:
            raw.append(_from_analysis(incident_id, ar))
        except Exception:
            pass

    for ra in remediation_actions:
        try:
            raw.extend(_from_action(incident_id, ra))
        except Exception:
            pass

    for al in audit_logs:
        try:
            evt = _from_audit(incident_id, al)
            if evt is not None:
                raw.append(evt)
        except Exception:
            pass

    # Deduplicate: keep first occurrence (sources produce deterministic IDs)
    seen: set[str] = set()
    deduped: list[TimelineEvent] = []
    for evt in raw:
        if evt.id not in seen:
            seen.add(evt.id)
            deduped.append(evt)

    deduped.sort(key=lambda e: e.timestamp)
    return deduped
