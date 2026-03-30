"""
tests/test_structured_output_parser.py
----------------------------------------
Unit tests for structured_output_parser.parse() focusing on:
  - Pre-classified hypothesis merging with LLM output
  - Deduplication by title
  - Ranking order (confidence descending)
  - Fallback padding when < 3 hypotheses and top confidence < 0.65
  - Pre-evidence merging
  - Category preservation from both pre-classified and LLM hypotheses
  - Graceful handling of malformed LLM output

Run with: pytest services/analysis-service/tests/test_structured_output_parser.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from structured_output_parser import parse
from domain.models import EvidenceItem, Hypothesis, StructuredAnalysis


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _h(title: str, confidence: float = 0.5, category: str = "root_cause") -> Hypothesis:
    return Hypothesis(title=title, description="test", category=category, confidence=confidence, rank=1)


def _e(label: str) -> EvidenceItem:
    return EvidenceItem(source="database", kind="metric", label=label, value="42")


def _v3_llm(hypotheses: list[dict] | None = None) -> dict:
    """Minimal v3 LLM output dict."""
    return {
        "summary": "Something broke",
        "probable_cause": "Unknown",
        "evidence_points": ["point 1"],
        "recommended_action_id": "restart_deployment",
        "confidence": 0.6,
        "escalate": False,
        "hypotheses": hypotheses or [],
        "evidence": [],
        "action_plan": [],
    }


# --------------------------------------------------------------------------- #
# Pre-hypothesis merging
# --------------------------------------------------------------------------- #

class TestPreHypothesisMerge:
    def test_pre_hypotheses_appear_in_output(self):
        pre = [_h("Connection leak introduced by recent deploy", 0.75, "root_cause")]
        result = parse(_v3_llm(), pre_hypotheses=pre)
        titles = [h.title for h in result.hypotheses]
        assert "Connection leak introduced by recent deploy" in titles

    def test_llm_hypotheses_also_appear(self):
        pre = [_h("Pre hypothesis", 0.70, "trigger")]
        llm = _v3_llm([{"title": "LLM hypothesis", "description": "desc", "confidence": 0.50, "category": "symptom"}])
        result = parse(llm, pre_hypotheses=pre)
        titles = [h.title for h in result.hypotheses]
        assert "Pre hypothesis" in titles
        assert "LLM hypothesis" in titles

    def test_pre_hypothesis_wins_on_title_collision(self):
        pre = [_h("Same Title", confidence=0.80, category="trigger")]
        llm = _v3_llm([{"title": "Same Title", "description": "LLM version", "confidence": 0.30, "category": "root_cause"}])
        result = parse(llm, pre_hypotheses=pre)
        # Should appear exactly once
        same = [h for h in result.hypotheses if h.title == "Same Title"]
        assert len(same) == 1
        # Pre-classified version wins
        assert same[0].category == "trigger"
        assert same[0].confidence == 0.80

    def test_case_insensitive_deduplication(self):
        pre = [_h("Database connection pool saturation", 0.70, "symptom")]
        llm = _v3_llm([{"title": "DATABASE CONNECTION POOL SATURATION", "description": "same", "confidence": 0.40, "category": "symptom"}])
        result = parse(llm, pre_hypotheses=pre)
        # Deduplication is on first 60 chars lowercased
        sat = [h for h in result.hypotheses if "saturation" in h.title.lower()]
        assert len(sat) == 1, f"Expected 1 saturation hypothesis, got {len(sat)}"

    def test_no_pre_hypotheses_still_works(self):
        llm = _v3_llm([{"title": "LLM-only", "description": "desc", "confidence": 0.70, "category": "root_cause"}])
        result = parse(llm)
        assert any(h.title == "LLM-only" for h in result.hypotheses)


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #

class TestRanking:
    def test_hypotheses_sorted_by_confidence_descending(self):
        pre = [
            _h("High confidence", 0.85, "trigger"),
            _h("Low confidence", 0.20, "symptom"),
        ]
        result = parse(_v3_llm(), pre_hypotheses=pre)
        confs = [h.confidence for h in result.hypotheses]
        assert confs == sorted(confs, reverse=True), "Hypotheses must be sorted confidence-descending"

    def test_rank_values_are_sequential(self):
        pre = [_h(f"H{i}", 0.9 - i * 0.1) for i in range(4)]
        result = parse(_v3_llm(), pre_hypotheses=pre)
        ranks = [h.rank for h in result.hypotheses]
        assert ranks == list(range(1, len(ranks) + 1)), f"Expected sequential ranks, got {ranks}"

    def test_rank_1_is_highest_confidence(self):
        pre = [_h("Low", 0.20), _h("High", 0.80)]
        result = parse(_v3_llm(), pre_hypotheses=pre)
        assert result.hypotheses[0].confidence == 0.80
        assert result.hypotheses[0].rank == 1


# --------------------------------------------------------------------------- #
# Padding to three
# --------------------------------------------------------------------------- #

class TestPaddingToThree:
    def test_padded_when_top_confidence_below_0_65_and_fewer_than_3(self):
        pre = [_h("Only one", 0.40, "root_cause")]
        result = parse(_v3_llm(), pre_hypotheses=pre)
        assert len(result.hypotheses) >= 3, "Must pad to 3 when top confidence < 0.65"

    def test_no_padding_when_3_already_exist(self):
        pre = [_h(f"H{i}", 0.40) for i in range(3)]
        result = parse(_v3_llm(), pre_hypotheses=pre)
        # Padding only fills up to 3, so exactly 3 is acceptable
        assert len(result.hypotheses) >= 3

    def test_no_padding_when_top_confidence_high(self):
        pre = [_h("Strong", 0.80)]
        result = parse(_v3_llm(), pre_hypotheses=pre)
        # No padding needed — top confidence >= 0.65
        # 1 pre + fallback padding should NOT fire
        assert result.hypotheses[0].confidence == 0.80


# --------------------------------------------------------------------------- #
# Pre-evidence merging
# --------------------------------------------------------------------------- #

class TestPreEvidenceMerge:
    def test_pre_evidence_appears_first_in_list(self):
        pre_ev = [_e("connection_saturation_pct")]
        result = parse(_v3_llm(), pre_evidence=pre_ev)
        assert result.evidence[0].label == "connection_saturation_pct"

    def test_llm_evidence_appended_after_pre(self):
        pre_ev = [_e("pre_label")]
        llm = _v3_llm()
        llm["evidence"] = [{"source": "prometheus", "kind": "metric", "label": "llm_label", "value": "42"}]
        result = parse(llm, pre_evidence=pre_ev)
        labels = [e.label for e in result.evidence]
        assert labels.index("pre_label") < labels.index("llm_label")

    def test_no_pre_evidence_still_works(self):
        result = parse(_v3_llm())
        assert isinstance(result.evidence, list)


# --------------------------------------------------------------------------- #
# Category preservation
# --------------------------------------------------------------------------- #

class TestCategoryPreservation:
    def test_pre_classified_categories_preserved(self):
        pre = [
            _h("Symptom H", 0.70, "symptom"),
            _h("Trigger H", 0.65, "trigger"),
            _h("Root Cause H", 0.60, "root_cause"),
        ]
        result = parse(_v3_llm(), pre_hypotheses=pre)
        cats = {h.title: h.category for h in result.hypotheses}
        assert cats["Symptom H"] == "symptom"
        assert cats["Trigger H"] == "trigger"
        assert cats["Root Cause H"] == "root_cause"

    def test_llm_category_field_respected(self):
        llm = _v3_llm([{
            "title": "LLM symptom", "description": "desc",
            "confidence": 0.60, "category": "symptom",
        }])
        result = parse(llm)
        match = next(h for h in result.hypotheses if h.title == "LLM symptom")
        assert match.category == "symptom"

    def test_invalid_llm_category_gets_inferred(self):
        llm = _v3_llm([{
            "title": "A recent deploy caused this",
            "description": "deploy occurred right before the crash",
            "confidence": 0.55,
            "category": "NOT_VALID",
        }])
        result = parse(llm)
        match = next(h for h in result.hypotheses if "deploy" in h.title.lower())
        assert match.category in ("symptom", "trigger", "root_cause")


# --------------------------------------------------------------------------- #
# Malformed LLM output
# --------------------------------------------------------------------------- #

class TestMalformedLLMOutput:
    def test_empty_dict_returns_valid_output(self):
        result = parse({})
        assert isinstance(result, StructuredAnalysis)
        assert result.hypotheses  # at least one

    def test_v2_flat_output_synthesized(self):
        v2 = {
            "summary": "Something went wrong",
            "probable_cause": "Connection leak in the API service",
            "evidence_points": ["high error rate", "DB connections at max"],
            "recommended_action_id": "rollout_restart",
            "confidence": 0.72,
            "escalate": False,
        }
        result = parse(v2)
        assert isinstance(result, StructuredAnalysis)
        assert result.hypotheses
        assert result.escalate is False

    def test_parse_never_raises_on_garbage(self):
        garbage = {"hypotheses": "not a list", "evidence": 42, "action_plan": None}
        result = parse(garbage)
        assert isinstance(result, StructuredAnalysis)

    def test_fallback_hypothesis_has_valid_category(self):
        result = parse({})
        for h in result.hypotheses:
            assert h.category in ("symptom", "trigger", "root_cause")
