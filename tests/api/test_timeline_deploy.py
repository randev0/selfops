"""
test_timeline_deploy.py
-----------------------
Unit tests for _from_deploy_correlation in the timeline aggregator.

Verifies that deploy_correlation IncidentEvidence rows are correctly
converted to TimelineEvent(source="deploy") objects.
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.timeline.aggregator import _from_deploy_correlation

_INC_TS = datetime(2025, 3, 1, 14, 0, 0, tzinfo=timezone.utc)


def _dt(offset_minutes: int = 0) -> datetime:
    return _INC_TS + timedelta(minutes=offset_minutes)


def _ev(content: dict):
    return SimpleNamespace(
        id=uuid.uuid4(),
        evidence_type="deploy_correlation",
        content=content,
        captured_at=_INC_TS,
    )


def _make_content(
    *,
    deploys=None,
    likely_regression=False,
    minutes=None,
    closest=None,
    available=True,
):
    return {
        "available": available,
        "repo": "org/repo",
        "service": "svc",
        "incident_timestamp": _INC_TS.isoformat(),
        "recent_deploys": deploys or [],
        "likely_regression": likely_regression,
        "regression_window_minutes": minutes,
        "closest_deploy": closest,
    }


def _make_deploy(kind: str = "release", offset_minutes: int = -30) -> dict:
    return {
        "id": f"d-{abs(offset_minutes)}",
        "kind": kind,
        "ref": "v1.2.3",
        "timestamp": _dt(offset_minutes).isoformat(),
        "title": f"Deploy at -{abs(offset_minutes)}m",
        "author": "ci",
        "url": None,
        "commit_sha": "abc1234",
        "image_tag_hint": None,
    }


_INC_UUID = uuid.uuid4()


# --------------------------------------------------------------------------- #
# Basic emission
# --------------------------------------------------------------------------- #


def test_deploy_events_emitted_for_each_deploy():
    content = _make_content(deploys=[_make_deploy(-30), _make_deploy(-90)])
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    deploy_events = [e for e in events if e.event_type.startswith("deploy.")]
    assert len(deploy_events) == 2


def test_unavailable_context_returns_empty():
    events = _from_deploy_correlation(_INC_UUID, _ev({"available": False}))
    assert events == []


def test_empty_deploys_returns_empty():
    content = _make_content(deploys=[])
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    assert events == []


# --------------------------------------------------------------------------- #
# Regression warning
# --------------------------------------------------------------------------- #


def test_regression_warning_emitted_when_likely_regression():
    closest = _make_deploy(-30)
    content = _make_content(
        deploys=[closest],
        likely_regression=True,
        minutes=30,
        closest=closest,
    )
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    regression = [e for e in events if e.event_type == "deploy.regression_suspected"]
    assert len(regression) == 1
    assert regression[0].severity == "warning"


def test_no_regression_event_when_not_likely():
    content = _make_content(deploys=[_make_deploy(-90)], likely_regression=False)
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    assert not any(e.event_type == "deploy.regression_suspected" for e in events)


def test_regression_description_mentions_minutes():
    closest = _make_deploy(-45)
    content = _make_content(
        deploys=[closest],
        likely_regression=True,
        minutes=45,
        closest=closest,
    )
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    reg = next(e for e in events if e.event_type == "deploy.regression_suspected")
    assert "45" in reg.description


# --------------------------------------------------------------------------- #
# Source and event_type values
# --------------------------------------------------------------------------- #


def test_deploy_event_source_is_deploy():
    content = _make_content(deploys=[_make_deploy(-20)])
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    for e in events:
        assert e.source == "deploy"


def test_release_kind_produces_deploy_release_event_type():
    content = _make_content(deploys=[_make_deploy(kind="release", offset_minutes=-10)])
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    evt = next(e for e in events if e.event_type.startswith("deploy."))
    assert evt.event_type == "deploy.release"


def test_pr_merge_kind_produces_deploy_pr_merge_event_type():
    content = _make_content(deploys=[_make_deploy(kind="pr_merge", offset_minutes=-10)])
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    evt = next(e for e in events if e.event_type.startswith("deploy."))
    assert evt.event_type == "deploy.pr_merge"


def test_unknown_kind_produces_deploy_change_event_type():
    d = _make_deploy(-10)
    d["kind"] = "something_new"
    content = _make_content(deploys=[d])
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    evt = next((e for e in events if e.event_type != "deploy.regression_suspected"), None)
    assert evt is not None
    assert evt.event_type == "deploy.change"


# --------------------------------------------------------------------------- #
# Deduplication and uniqueness
# --------------------------------------------------------------------------- #


def test_event_ids_unique():
    content = _make_content(
        deploys=[_make_deploy(offset_minutes=-20), _make_deploy(offset_minutes=-60)]
    )
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    ids = [e.id for e in events]
    assert len(ids) == len(set(ids))


def test_two_evidence_rows_produce_distinct_event_ids():
    """Different evidence DB rows must produce different event IDs."""
    content = _make_content(deploys=[_make_deploy(-20)])
    ev1 = _ev(content)
    ev2 = _ev(content)
    events1 = _from_deploy_correlation(_INC_UUID, ev1)
    events2 = _from_deploy_correlation(_INC_UUID, ev2)
    ids1 = {e.id for e in events1}
    ids2 = {e.id for e in events2}
    assert ids1.isdisjoint(ids2)


# --------------------------------------------------------------------------- #
# Resilience / malformed data
# --------------------------------------------------------------------------- #


def test_malformed_deploy_entry_skipped():
    content = _make_content(
        deploys=[
            "not-a-dict",
            None,
            {"id": "ok", "kind": "release", "timestamp": _dt(-10).isoformat(), "title": "Good"},
        ]
    )
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    deploy_evts = [e for e in events if e.event_type.startswith("deploy.")]
    assert len(deploy_evts) == 1


def test_bad_timestamp_in_deploy_skips_entry():
    d = _make_deploy(-10)
    d["timestamp"] = "not-a-date"
    content = _make_content(deploys=[d])
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    assert events == []


def test_none_content_returns_empty():
    ev = SimpleNamespace(
        id=uuid.uuid4(),
        evidence_type="deploy_correlation",
        content=None,
        captured_at=_INC_TS,
    )
    events = _from_deploy_correlation(_INC_UUID, ev)
    assert events == []


def test_all_required_fields_present():
    content = _make_content(deploys=[_make_deploy(-20)])
    events = _from_deploy_correlation(_INC_UUID, _ev(content))
    for e in events:
        assert e.id
        assert e.incident_id == str(_INC_UUID)
        assert e.timestamp is not None
        assert e.event_type
        assert e.source == "deploy"
        assert e.title
        assert e.description is not None
