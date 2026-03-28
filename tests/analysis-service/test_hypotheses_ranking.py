"""
test_hypotheses_ranking.py
---------------------------
Tests for hypothesis confidence ranking, rank assignment, and the
ambiguity-padding rule (≥3 hypotheses when top confidence < 0.65).
"""

import pytest
import structured_output_parser as sop
from domain.models import Hypothesis


def _flat(hypotheses: list[dict], confidence: float = 0.5) -> dict:
    return {
        "summary": "test summary",
        "probable_cause": "test cause",
        "evidence_points": [],
        "confidence": confidence,
        "escalate": False,
        "hypotheses": hypotheses,
    }


# --------------------------------------------------------------------------- #
# Rank assignment
# --------------------------------------------------------------------------- #

def test_rank_1_is_highest_confidence():
    result = sop.parse(_flat([
        {"title": "Cause A", "description": "A", "confidence": 0.3, "supporting_evidence": []},
        {"title": "Cause B", "description": "B", "confidence": 0.7, "supporting_evidence": []},
    ]))
    assert result.hypotheses[0].rank == 1
    assert result.hypotheses[0].confidence == pytest.approx(0.7, abs=0.001)


def test_ranks_are_sequential():
    result = sop.parse(_flat([
        {"title": f"Cause {i}", "description": "x", "confidence": 0.9 - i * 0.1, "supporting_evidence": []}
        for i in range(4)
    ]))
    ranks = [h.rank for h in result.hypotheses]
    assert sorted(ranks) == list(range(1, len(ranks) + 1))


def test_descending_order_by_confidence():
    result = sop.parse(_flat([
        {"title": "Low", "description": "x", "confidence": 0.2, "supporting_evidence": []},
        {"title": "High", "description": "x", "confidence": 0.9, "supporting_evidence": []},
        {"title": "Mid", "description": "x", "confidence": 0.5, "supporting_evidence": []},
    ]))
    confs = [h.confidence for h in result.hypotheses]
    assert confs == sorted(confs, reverse=True)


def test_equal_confidence_all_rank_assigned():
    result = sop.parse(_flat([
        {"title": "A", "description": "x", "confidence": 0.5, "supporting_evidence": []},
        {"title": "B", "description": "x", "confidence": 0.5, "supporting_evidence": []},
    ]))
    ranks = {h.rank for h in result.hypotheses}
    assert len(ranks) == len(result.hypotheses)  # all ranks unique


# --------------------------------------------------------------------------- #
# Ambiguity padding (top confidence < 0.65 → at least 3 hypotheses)
# --------------------------------------------------------------------------- #

def test_padding_to_three_when_ambiguous():
    result = sop.parse(_flat([
        {"title": "Cause A", "description": "A", "confidence": 0.6, "supporting_evidence": []},
    ]))
    assert len(result.hypotheses) >= 3


def test_no_padding_when_confident():
    result = sop.parse(_flat([
        {"title": "Clear cause", "description": "C", "confidence": 0.95, "supporting_evidence": []},
    ]))
    # Only 1 high-confidence hypothesis — should NOT be padded to 3
    assert len(result.hypotheses) == 1


def test_no_padding_when_already_three():
    result = sop.parse(_flat([
        {"title": "A", "description": "x", "confidence": 0.4, "supporting_evidence": []},
        {"title": "B", "description": "x", "confidence": 0.3, "supporting_evidence": []},
        {"title": "C", "description": "x", "confidence": 0.2, "supporting_evidence": []},
    ]))
    # already 3, should not add more
    assert len(result.hypotheses) == 3


def test_padding_produces_nonzero_confidence():
    result = sop.parse(_flat([
        {"title": "Weak cause", "description": "x", "confidence": 0.4, "supporting_evidence": []},
    ]))
    padded = result.hypotheses[1:]  # everything after the first
    assert all(h.confidence > 0.0 for h in padded)


def test_padded_hypotheses_have_unique_titles():
    result = sop.parse(_flat([
        {"title": "Weak cause", "description": "x", "confidence": 0.4, "supporting_evidence": []},
    ]))
    titles = [h.title for h in result.hypotheses]
    assert len(titles) == len(set(titles))


def test_padded_titles_differ_from_original():
    result = sop.parse(_flat([
        {"title": "Transient infrastructure failure", "description": "x", "confidence": 0.4, "supporting_evidence": []},
    ]))
    # The fallback candidate with this title should NOT be duplicated
    titles_lower = [h.title.lower() for h in result.hypotheses]
    assert titles_lower.count("transient infrastructure failure") == 1


def test_confidence_clamped_above_1():
    result = sop.parse(_flat([
        {"title": "A", "description": "x", "confidence": 1.5, "supporting_evidence": []},
    ]))
    assert all(h.confidence <= 1.0 for h in result.hypotheses)


def test_confidence_clamped_below_0():
    result = sop.parse(_flat([
        {"title": "A", "description": "x", "confidence": -0.3, "supporting_evidence": []},
    ]))
    assert all(h.confidence >= 0.0 for h in result.hypotheses)
