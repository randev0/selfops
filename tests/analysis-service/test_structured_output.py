"""
test_structured_output.py
--------------------------
Tests for structured_output_parser.parse() with a well-formed v3 LLM response.
"""

import pytest

import structured_output_parser as sop
from domain.models import StructuredAnalysis, EvidenceItem, Hypothesis, ActionPlanItem


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def v3_response():
    """A realistic v3 LLM JSON dict with all structured fields present."""
    return {
        "summary": "The payment-worker pod is crash-looping due to OOM kills.",
        "probable_cause": "Memory leak in the payment processing loop exceeds the 256Mi limit.",
        "evidence_points": ["5 restarts in 5 min", "OOMKilled in last event"],
        "recommended_action_id": "rollout_restart",
        "confidence": 0.82,
        "escalate": False,
        "evidence": [
            {
                "source": "prometheus",
                "kind": "metric",
                "label": "restart_count",
                "value": "5 restarts in last 5 minutes",
            },
            {
                "source": "k8s",
                "kind": "resource",
                "label": "last_termination_reason",
                "value": "OOMKilled",
            },
        ],
        "hypotheses": [
            {
                "title": "Memory leak in payment loop",
                "description": "The payment processing coroutine accumulates heap objects without releasing them.",
                "confidence": 0.82,
                "supporting_evidence": ["restart_count", "last_termination_reason"],
            },
            {
                "title": "Memory limit too low",
                "description": "The 256Mi limit is insufficient for peak transaction volumes.",
                "confidence": 0.14,
                "supporting_evidence": ["restart_count"],
            },
        ],
        "action_plan": [
            {
                "action_id": "rollout_restart",
                "description": "Rolling restart clears leaked heap and restores service temporarily.",
                "risk_level": "low",
                "verification_steps": [
                    {"description": "Rollout completes", "check": "rollout_status == complete"},
                    {"description": "No new OOM kills", "check": "oomkill_count_5m == 0"},
                ],
            }
        ],
    }


# --------------------------------------------------------------------------- #
# Basic structure tests
# --------------------------------------------------------------------------- #

def test_parse_returns_structured_analysis(v3_response):
    result = sop.parse(v3_response)
    assert isinstance(result, StructuredAnalysis)


def test_incident_summary_populated(v3_response):
    result = sop.parse(v3_response)
    assert "payment-worker" in result.incident_summary
    assert len(result.incident_summary) > 0


def test_evidence_items_typed(v3_response):
    result = sop.parse(v3_response)
    assert len(result.evidence) == 2
    prom = next(e for e in result.evidence if e.source == "prometheus")
    k8s = next(e for e in result.evidence if e.source == "k8s")
    assert prom.kind == "metric"
    assert k8s.kind == "resource"
    assert prom.label == "restart_count"


def test_evidence_value_truncated_at_500(v3_response):
    v3_response["evidence"][0]["value"] = "x" * 1000
    result = sop.parse(v3_response)
    assert all(len(e.value) <= 500 for e in result.evidence)


def test_evidence_label_truncated_at_100(v3_response):
    v3_response["evidence"][0]["label"] = "a" * 200
    result = sop.parse(v3_response)
    assert all(len(e.label) <= 100 for e in result.evidence)


def test_recommended_action_id_propagated(v3_response):
    result = sop.parse(v3_response)
    assert result.recommended_action_id == "rollout_restart"


def test_overall_confidence_in_range(v3_response):
    result = sop.parse(v3_response)
    assert 0.0 <= result.overall_confidence <= 1.0
    assert result.overall_confidence == pytest.approx(0.82, abs=0.001)


def test_escalate_false_by_default(v3_response):
    result = sop.parse(v3_response)
    assert result.escalate is False


# --------------------------------------------------------------------------- #
# Action plan tests
# --------------------------------------------------------------------------- #

def test_action_plan_populated(v3_response):
    result = sop.parse(v3_response)
    assert len(result.action_plan) == 1
    action = result.action_plan[0]
    assert isinstance(action, ActionPlanItem)
    assert action.action_id == "rollout_restart"


def test_action_risk_level_valid(v3_response):
    result = sop.parse(v3_response)
    for action in result.action_plan:
        assert action.risk_level in ("low", "medium", "high")


def test_action_requires_approval_bool(v3_response):
    result = sop.parse(v3_response)
    for action in result.action_plan:
        assert isinstance(action.requires_approval, bool)


def test_action_verification_steps_present(v3_response):
    result = sop.parse(v3_response)
    action = result.action_plan[0]
    assert len(action.verification_steps) >= 1
    for step in action.verification_steps:
        assert step.description
        assert step.check


def test_invalid_risk_level_coerced_to_medium(v3_response):
    v3_response["action_plan"][0]["risk_level"] = "extreme"
    result = sop.parse(v3_response)
    assert result.action_plan[0].risk_level == "medium"


def test_unknown_source_coerced_to_other():
    flat = {
        "summary": "test",
        "probable_cause": "test",
        "confidence": 0.5,
        "evidence_points": [],
        "evidence": [
            {"source": "datadog", "kind": "metric", "label": "foo", "value": "1"}
        ],
    }
    result = sop.parse(flat)
    assert result.evidence[0].source == "other"


def test_unknown_kind_coerced_to_metric():
    flat = {
        "summary": "test",
        "probable_cause": "test",
        "confidence": 0.5,
        "evidence_points": [],
        "evidence": [
            {"source": "prometheus", "kind": "trace", "label": "foo", "value": "1"}
        ],
    }
    result = sop.parse(flat)
    assert result.evidence[0].kind == "metric"
