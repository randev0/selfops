"""
test_backward_compat.py
------------------------
Verifies that:
  1. AnalysisResponse still exposes all v2 flat fields unchanged.
  2. structured_output_parser.parse() handles v2-only dicts (no hypotheses /
     evidence / action_plan keys) and returns a valid StructuredAnalysis.
  3. structured field is Optional — consumers that ignore it still work.
  4. Existing field names and types match what the worker and frontend expect.
"""

import pytest

from schemas import AnalysisResponse
from domain.models import StructuredAnalysis
import structured_output_parser as sop


# --------------------------------------------------------------------------- #
# AnalysisResponse backward-compat shape
# --------------------------------------------------------------------------- #

def _make_response(**overrides) -> AnalysisResponse:
    defaults = dict(
        summary="Pod is crash-looping",
        probable_cause="OOM kill due to memory leak",
        evidence_points=["5 restarts", "OOMKilled"],
        recommended_action_id="rollout_restart",
        confidence=0.85,
        escalate=False,
        raw_output={"summary": "Pod is crash-looping"},
        investigation_log=[{"type": "thought", "content": "Checking metrics"}],
        structured=None,
    )
    defaults.update(overrides)
    return AnalysisResponse(**defaults)


def test_v2_fields_all_present():
    r = _make_response()
    assert r.summary == "Pod is crash-looping"
    assert r.probable_cause == "OOM kill due to memory leak"
    assert r.evidence_points == ["5 restarts", "OOMKilled"]
    assert r.recommended_action_id == "rollout_restart"
    assert r.confidence == 0.85
    assert r.escalate is False
    assert isinstance(r.raw_output, dict)
    assert isinstance(r.investigation_log, list)


def test_structured_field_is_optional():
    r = _make_response(structured=None)
    assert r.structured is None


def test_structured_field_accepts_structured_analysis():
    sa = StructuredAnalysis(
        incident_summary="pod oom",
        overall_confidence=0.85,
        escalate=False,
        hypotheses=[],
    )
    r = _make_response(structured=sa)
    assert r.structured is not None
    assert r.structured.incident_summary == "pod oom"


def test_investigation_log_optional():
    r = _make_response(investigation_log=None)
    assert r.investigation_log is None


def test_recommended_action_id_optional():
    r = _make_response(recommended_action_id=None)
    assert r.recommended_action_id is None


# --------------------------------------------------------------------------- #
# Parser handles v2 flat dicts (no new keys)
# --------------------------------------------------------------------------- #

V2_FLAT = {
    "summary": "Pod is crash-looping in namespace platform.",
    "probable_cause": "Memory leak causing OOMKill after startup.",
    "evidence_points": ["restart_count=5", "OOMKilled event"],
    "recommended_action_id": "rollout_restart",
    "confidence": 0.78,
    "escalate": False,
}


def test_v2_flat_parses_without_error():
    result = sop.parse(V2_FLAT)
    assert isinstance(result, StructuredAnalysis)


def test_v2_flat_incident_summary_from_summary():
    result = sop.parse(V2_FLAT)
    assert "crash-looping" in result.incident_summary


def test_v2_flat_hypothesis_title_from_probable_cause():
    result = sop.parse(V2_FLAT)
    # probable_cause becomes the first hypothesis title
    first = result.hypotheses[0]
    assert "Memory leak" in first.title or "Memory leak" in first.description


def test_v2_flat_confidence_propagated():
    result = sop.parse(V2_FLAT)
    assert result.overall_confidence == pytest.approx(0.78, abs=0.001)


def test_v2_flat_action_plan_from_recommended_id():
    result = sop.parse(V2_FLAT)
    assert len(result.action_plan) >= 1
    assert result.action_plan[0].action_id == "rollout_restart"


def test_v2_flat_evidence_from_evidence_points():
    result = sop.parse(V2_FLAT)
    assert len(result.evidence) == 2
    values = [e.value for e in result.evidence]
    assert "restart_count=5" in values


def test_v2_flat_recommended_action_id_preserved():
    result = sop.parse(V2_FLAT)
    assert result.recommended_action_id == "rollout_restart"


def test_v2_flat_escalate_preserved():
    result = sop.parse(V2_FLAT)
    assert result.escalate is False


def test_v2_flat_escalate_true_preserved():
    flat = dict(V2_FLAT, escalate=True)
    result = sop.parse(flat)
    assert result.escalate is True


# --------------------------------------------------------------------------- #
# prompt_version compatibility: existing 'v2-react' analysis rows
# The worker now writes 'v3-structured'; old rows with 'v2-react' stay valid.
# --------------------------------------------------------------------------- #

def test_v2_schema_serialises_to_dict():
    """AnalysisResponse must be JSON-serialisable (required by FastAPI)."""
    r = _make_response()
    d = r.model_dump()
    assert d["summary"] == "Pod is crash-looping"
    assert d["structured"] is None


def test_v3_schema_serialises_structured():
    sa = StructuredAnalysis(
        incident_summary="crash",
        overall_confidence=0.9,
        escalate=False,
        hypotheses=[],
    )
    r = _make_response(structured=sa)
    d = r.model_dump()
    assert d["structured"]["incident_summary"] == "crash"
    assert d["structured"]["overall_confidence"] == pytest.approx(0.9, abs=0.001)
