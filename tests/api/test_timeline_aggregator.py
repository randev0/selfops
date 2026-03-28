"""
test_timeline_aggregator.py
----------------------------
Unit tests for app.timeline.aggregator.build_timeline.

All tests work purely in-memory using SimpleNamespace stubs — no database
or FastAPI server is required.
"""
import uuid
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.timeline.aggregator import build_timeline, _ts
from app.timeline.models import TimelineEvent


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

INC = uuid.uuid4()
_TS_BASE = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _dt(offset_seconds: int = 0) -> datetime:
    return _TS_BASE + timedelta(seconds=offset_seconds)


def _alert(
    *,
    id: uuid.UUID | None = None,
    alert_name: str = "TestAlert",
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    created_at: datetime | None = None,
    labels: dict | None = None,
    annotations: dict | None = None,
) -> Any:
    return SimpleNamespace(
        id=id or uuid.uuid4(),
        alert_name=alert_name,
        starts_at=starts_at,
        ends_at=ends_at,
        created_at=created_at or _dt(),
        labels=labels or {},
        annotations=annotations or {},
    )


_UNSET = object()


def _evidence(
    *,
    id: uuid.UUID | None = None,
    evidence_type: str = "metric",
    content: dict | None = None,
    captured_at: Any = _UNSET,
) -> Any:
    return SimpleNamespace(
        id=id or uuid.uuid4(),
        evidence_type=evidence_type,
        content=content if content is not None else {},
        captured_at=_dt() if captured_at is _UNSET else captured_at,
    )


def _analysis(
    *,
    id: uuid.UUID | None = None,
    model_name: str = "claude-3-haiku",
    summary: str | None = "Test summary",
    probable_cause: str | None = None,
    confidence_score: float | None = 0.8,
    escalate: bool = False,
    created_at: datetime | None = None,
) -> Any:
    return SimpleNamespace(
        id=id or uuid.uuid4(),
        model_name=model_name,
        summary=summary,
        probable_cause=probable_cause,
        confidence_score=confidence_score,
        escalate=escalate,
        created_at=created_at or _dt(),
    )


def _action(
    *,
    id: uuid.UUID | None = None,
    action_name: str = "Rollout Restart",
    action_type: str = "rollout_restart",
    requested_by: str = "operator",
    status: Any = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    result_summary: str | None = None,
    pr_url: str | None = None,
    created_at: datetime | None = None,
) -> Any:
    class _Status:
        def __init__(self, v):
            self.value = v

    return SimpleNamespace(
        id=id or uuid.uuid4(),
        action_name=action_name,
        action_type=action_type,
        requested_by=requested_by,
        status=_Status(status) if status else None,
        started_at=started_at,
        completed_at=completed_at,
        result_summary=result_summary,
        pr_url=pr_url,
        created_at=created_at or _dt(),
    )


def _audit(
    *,
    id: uuid.UUID | None = None,
    event_type: str = "incident.created",
    message: str = "Incident created",
    actor_type: str = "system",
    actor_id: str = "system",
    created_at: datetime | None = None,
) -> Any:
    return SimpleNamespace(
        id=id or uuid.uuid4(),
        event_type=event_type,
        message=message,
        actor_type=actor_type,
        actor_id=actor_id,
        created_at=created_at or _dt(),
    )


def _build(**kwargs) -> list[TimelineEvent]:
    defaults = dict(
        incident_id=INC,
        alert_events=[],
        evidence=[],
        analysis_results=[],
        remediation_actions=[],
        audit_logs=[],
    )
    defaults.update(kwargs)
    return build_timeline(**defaults)


# --------------------------------------------------------------------------- #
# Empty sources
# --------------------------------------------------------------------------- #


def test_empty_all_sources_returns_empty_list():
    assert _build() == []


def test_empty_alert_events_only_returns_empty():
    assert _build(alert_events=[]) == []


# --------------------------------------------------------------------------- #
# Single-source events
# --------------------------------------------------------------------------- #


def test_alert_event_produces_fired_event():
    events = _build(alert_events=[_alert(alert_name="PodCrashLooping")])
    types = [e.event_type for e in events]
    assert "alert.fired" in types


def test_alert_event_with_ends_at_produces_resolved_event():
    a = _alert(starts_at=_dt(0), ends_at=_dt(60))
    events = _build(alert_events=[a])
    types = [e.event_type for e in events]
    assert "alert.fired" in types
    assert "alert.resolved" in types


def test_alert_event_without_ends_at_no_resolved():
    a = _alert(ends_at=None)
    events = _build(alert_events=[a])
    assert all(e.event_type != "alert.resolved" for e in events)


def test_evidence_produces_evidence_collected():
    events = _build(evidence=[_evidence(evidence_type="metric")])
    assert any(e.event_type == "evidence.collected" for e in events)


def test_evidence_label_log():
    events = _build(evidence=[_evidence(evidence_type="log")])
    assert any("Logs" in e.title for e in events)


def test_analysis_produces_analysis_completed():
    events = _build(analysis_results=[_analysis()])
    assert any(e.event_type == "analysis.completed" for e in events)


def test_analysis_title_contains_confidence():
    events = _build(analysis_results=[_analysis(confidence_score=0.75)])
    desc = next(e.description for e in events if e.event_type == "analysis.completed")
    assert "75%" in desc


def test_analysis_none_confidence_shows_question_mark():
    events = _build(analysis_results=[_analysis(confidence_score=None)])
    desc = next(e.description for e in events if e.event_type == "analysis.completed")
    assert "?" in desc


def test_action_produces_requested_event():
    events = _build(remediation_actions=[_action()])
    assert any(e.event_type == "action.requested" for e in events)


def test_action_with_started_at_produces_started_event():
    a = _action(started_at=_dt(10))
    events = _build(remediation_actions=[a])
    assert any(e.event_type == "action.started" for e in events)


def test_action_success_produces_completed_event():
    a = _action(status="SUCCESS", completed_at=_dt(30))
    events = _build(remediation_actions=[a])
    assert any(e.event_type == "action.completed" for e in events)


def test_action_failure_produces_failed_event():
    a = _action(status="FAILED", completed_at=_dt(30))
    events = _build(remediation_actions=[a])
    assert any(e.event_type == "action.failed" for e in events)


def test_audit_produces_event_for_non_skipped_type():
    al = _audit(event_type="incident.created")
    events = _build(audit_logs=[al])
    assert any(e.event_type == "incident.created" for e in events)


def test_audit_skips_covered_event_types():
    skipped_types = [
        "action.requested",
        "action.completed",
        "analysis.completed",
        "alert.fired",
    ]
    for et in skipped_types:
        al = _audit(event_type=et)
        events = _build(audit_logs=[al])
        assert events == [], f"Expected skip for audit event_type={et!r}"


# --------------------------------------------------------------------------- #
# Chronological ordering
# --------------------------------------------------------------------------- #


def test_events_sorted_chronologically():
    ae = _alert(starts_at=_dt(30))
    ev = _evidence(captured_at=_dt(10))
    ar = _analysis(created_at=_dt(60))
    events = _build(alert_events=[ae], evidence=[ev], analysis_results=[ar])
    timestamps = [e.timestamp for e in events]
    assert timestamps == sorted(timestamps)


def test_multiple_alerts_ordered():
    a1 = _alert(starts_at=_dt(100), alert_name="Second")
    a2 = _alert(starts_at=_dt(50), alert_name="First")
    events = _build(alert_events=[a1, a2])
    # fired events only
    fired = [e for e in events if e.event_type == "alert.fired"]
    assert fired[0].timestamp < fired[1].timestamp


def test_resolved_event_after_fired_event():
    a = _alert(starts_at=_dt(0), ends_at=_dt(120))
    events = _build(alert_events=[a])
    fired_ts = next(e.timestamp for e in events if e.event_type == "alert.fired")
    resolved_ts = next(e.timestamp for e in events if e.event_type == "alert.resolved")
    assert fired_ts < resolved_ts


# --------------------------------------------------------------------------- #
# Deduplication
# --------------------------------------------------------------------------- #


def test_duplicate_evidence_entries_deduped():
    shared_id = uuid.uuid4()
    ev1 = _evidence(id=shared_id, evidence_type="metric")
    ev2 = _evidence(id=shared_id, evidence_type="metric")
    events = _build(evidence=[ev1, ev2])
    ids = [e.id for e in events]
    assert len(ids) == len(set(ids))
    assert len(events) == 1


def test_duplicate_audit_entries_deduped():
    shared_id = uuid.uuid4()
    al1 = _audit(id=shared_id, event_type="incident.created")
    al2 = _audit(id=shared_id, event_type="incident.created")
    events = _build(audit_logs=[al1, al2])
    assert len(events) == 1


# --------------------------------------------------------------------------- #
# Missing / bad timestamps
# --------------------------------------------------------------------------- #


def test_missing_starts_at_falls_back_to_created_at():
    created = _dt(200)
    a = _alert(starts_at=None, created_at=created)
    events = _build(alert_events=[a])
    fired = next(e for e in events if e.event_type == "alert.fired")
    assert fired.timestamp == created


def test_none_timestamp_treated_as_epoch():
    ev = _evidence(captured_at=None)
    events = _build(evidence=[ev])
    assert len(events) == 1
    epoch = datetime.fromtimestamp(0, tz=timezone.utc)
    assert events[0].timestamp == epoch


def test_naive_datetime_gets_utc():
    naive = datetime(2025, 6, 1, 10, 0, 0)  # no tzinfo
    ev = _evidence(captured_at=naive)
    events = _build(evidence=[ev])
    assert events[0].timestamp.tzinfo is not None


# --------------------------------------------------------------------------- #
# Malformed / missing data resilience
# --------------------------------------------------------------------------- #


def test_alert_with_none_labels_does_not_raise():
    a = _alert(labels=None, annotations=None)
    events = _build(alert_events=[a])
    assert len(events) >= 1


def test_evidence_with_none_content_does_not_raise():
    ev = _evidence(content=None)
    events = _build(evidence=[ev])
    assert len(events) == 1


def test_analysis_with_none_summary_does_not_raise():
    ar = _analysis(summary=None, probable_cause=None)
    events = _build(analysis_results=[ar])
    assert len(events) == 1


def test_action_with_no_started_or_completed_only_requested():
    a = _action(started_at=None, completed_at=None, status=None)
    events = _build(remediation_actions=[a])
    assert len(events) == 1
    assert events[0].event_type == "action.requested"


# --------------------------------------------------------------------------- #
# Multi-source merge
# --------------------------------------------------------------------------- #


def test_all_sources_produce_events():
    events = _build(
        alert_events=[_alert()],
        evidence=[_evidence()],
        analysis_results=[_analysis()],
        remediation_actions=[_action()],
        audit_logs=[_audit(event_type="incident.updated", message="Status changed")],
    )
    sources = {e.source for e in events}
    assert "alert" in sources
    assert "evidence" in sources
    assert "analysis" in sources
    assert "action" in sources
    assert "audit" in sources


def test_all_events_have_required_fields():
    events = _build(
        alert_events=[_alert()],
        evidence=[_evidence()],
        analysis_results=[_analysis()],
        remediation_actions=[_action()],
        audit_logs=[_audit()],
    )
    for e in events:
        assert e.id
        assert e.incident_id == str(INC)
        assert e.timestamp is not None
        assert e.event_type
        assert e.source
        assert e.title
        assert e.description is not None


def test_event_ids_unique_across_all_sources():
    events = _build(
        alert_events=[_alert(starts_at=_dt(0), ends_at=_dt(60))],
        evidence=[_evidence()],
        analysis_results=[_analysis()],
        remediation_actions=[_action(started_at=_dt(10), status="SUCCESS", completed_at=_dt(20))],
        audit_logs=[_audit(event_type="incident.created")],
    )
    ids = [e.id for e in events]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------- #
# _ts helper
# --------------------------------------------------------------------------- #


def test_ts_none_returns_epoch():
    epoch = datetime.fromtimestamp(0, tz=timezone.utc)
    assert _ts(None) == epoch


def test_ts_naive_adds_utc():
    naive = datetime(2024, 1, 1, 0, 0)
    result = _ts(naive)
    assert result.tzinfo is not None


def test_ts_aware_passes_through():
    aware = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert _ts(aware) == aware
