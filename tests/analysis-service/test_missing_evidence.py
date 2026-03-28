"""
test_missing_evidence.py
------------------------
Tests for edge cases where evidence, hypotheses, or action_plan fields are
absent, empty, None, or contain invalid entries.
"""

import pytest
import structured_output_parser as sop
from domain.models import StructuredAnalysis


# --------------------------------------------------------------------------- #
# Completely empty input
# --------------------------------------------------------------------------- #

def test_empty_dict_returns_structured_analysis():
    result = sop.parse({})
    assert isinstance(result, StructuredAnalysis)


def test_empty_dict_has_at_least_one_hypothesis():
    result = sop.parse({})
    assert len(result.hypotheses) >= 1


def test_empty_dict_hypothesis_rank_is_1():
    result = sop.parse({})
    assert result.hypotheses[0].rank == 1


def test_empty_dict_overall_confidence_is_zero():
    result = sop.parse({})
    assert result.overall_confidence == 0.0


def test_empty_dict_escalate_defaults_false():
    # default should be False unless the input says True
    result = sop.parse({})
    assert result.escalate is False


# --------------------------------------------------------------------------- #
# Missing evidence list
# --------------------------------------------------------------------------- #

def test_no_evidence_key_returns_empty_evidence():
    flat = {
        "summary": "test",
        "probable_cause": "cause",
        "confidence": 0.8,
        "evidence_points": [],
    }
    result = sop.parse(flat)
    assert result.evidence == []


def test_evidence_points_synthesized_as_evidence_items():
    flat = {
        "summary": "test",
        "probable_cause": "cause",
        "confidence": 0.8,
        "evidence_points": ["restart_count=5", "OOMKilled"],
    }
    result = sop.parse(flat)
    assert len(result.evidence) == 2
    assert all(e.kind == "alert" for e in result.evidence)
    assert all(e.source == "other" for e in result.evidence)


def test_invalid_evidence_entries_skipped():
    flat = {
        "summary": "test",
        "probable_cause": "cause",
        "confidence": 0.8,
        "evidence_points": [],
        "evidence": ["not a dict", 42, None, {"source": "prometheus", "kind": "metric", "label": "ok", "value": "1"}],
    }
    result = sop.parse(flat)
    assert len(result.evidence) == 1
    assert result.evidence[0].label == "ok"


# --------------------------------------------------------------------------- #
# Missing hypotheses
# --------------------------------------------------------------------------- #

def test_no_hypotheses_key_falls_back_to_probable_cause():
    flat = {
        "summary": "something broke",
        "probable_cause": "Memory leak in the worker",
        "confidence": 0.7,
        "evidence_points": [],
    }
    result = sop.parse(flat)
    assert len(result.hypotheses) >= 1
    assert "Memory leak" in result.hypotheses[0].title or "Memory leak" in result.hypotheses[0].description


def test_empty_hypotheses_list_falls_back():
    flat = {
        "summary": "test",
        "probable_cause": "Some cause",
        "confidence": 0.9,
        "evidence_points": [],
        "hypotheses": [],
    }
    result = sop.parse(flat)
    assert len(result.hypotheses) >= 1


def test_malformed_hypothesis_entries_skipped():
    flat = {
        "summary": "test",
        "probable_cause": "Backup cause",
        "confidence": 0.5,
        "evidence_points": [],
        "hypotheses": [
            "not a dict",
            None,
            {"title": "Valid", "description": "OK", "confidence": 0.5, "supporting_evidence": []},
        ],
    }
    result = sop.parse(flat)
    titles = [h.title for h in result.hypotheses]
    assert "Valid" in titles


# --------------------------------------------------------------------------- #
# Missing action plan
# --------------------------------------------------------------------------- #

def test_no_action_plan_with_recommended_id():
    flat = {
        "summary": "test",
        "probable_cause": "cause",
        "confidence": 0.8,
        "evidence_points": [],
        "recommended_action_id": "restart_deployment",
    }
    result = sop.parse(flat)
    assert len(result.action_plan) == 1
    assert result.action_plan[0].action_id == "restart_deployment"


def test_no_action_plan_no_recommended_id():
    flat = {
        "summary": "test",
        "probable_cause": "cause",
        "confidence": 0.8,
        "evidence_points": [],
        "recommended_action_id": None,
    }
    result = sop.parse(flat)
    assert result.action_plan == []


def test_default_verification_steps_injected_for_known_action():
    flat = {
        "summary": "test",
        "probable_cause": "cause",
        "confidence": 0.8,
        "evidence_points": [],
        "recommended_action_id": "restart_deployment",
    }
    result = sop.parse(flat)
    assert len(result.action_plan[0].verification_steps) >= 1


def test_default_verification_steps_injected_for_unknown_action():
    flat = {
        "summary": "test",
        "probable_cause": "cause",
        "confidence": 0.8,
        "evidence_points": [],
        "action_plan": [
            {
                "action_id": "unknown_action",
                "description": "some action",
                "risk_level": "medium",
            }
        ],
    }
    result = sop.parse(flat)
    assert len(result.action_plan[0].verification_steps) >= 1


def test_action_plan_empty_verification_steps_uses_defaults():
    flat = {
        "summary": "test",
        "probable_cause": "cause",
        "confidence": 0.8,
        "evidence_points": [],
        "action_plan": [
            {
                "action_id": "rollout_restart",
                "description": "restart",
                "risk_level": "low",
                "verification_steps": [],
            }
        ],
    }
    result = sop.parse(flat)
    # empty list → defaults injected
    assert len(result.action_plan[0].verification_steps) >= 1


# --------------------------------------------------------------------------- #
# Parser resilience
# --------------------------------------------------------------------------- #

def test_completely_broken_input_does_not_raise():
    result = sop.parse({"summary": None, "confidence": "not a float", "hypotheses": "bad"})
    assert isinstance(result, StructuredAnalysis)


def test_none_values_in_flat_fields_handled():
    result = sop.parse({
        "summary": None,
        "probable_cause": None,
        "confidence": None,
        "escalate": None,
        "evidence_points": None,
    })
    assert isinstance(result, StructuredAnalysis)
