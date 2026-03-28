"""
domain/models.py
----------------
Typed domain objects for structured incident analysis.

These are pure Pydantic value objects — no database or HTTP concerns here.
They represent the concepts the analyzer reasons about:

  EvidenceItem   — one piece of normalized evidence (metric, log line, k8s state, alert)
  Hypothesis     — a possible root cause with confidence score and supporting evidence
  VerificationStep — a single post-action health check
  ActionPlanItem — a proposed remediation with risk classification and verification steps
  StructuredAnalysis — the complete structured output of one analysis run

Relationships:
  StructuredAnalysis
    ├── evidence:    list[EvidenceItem]
    ├── hypotheses:  list[Hypothesis]   (sorted by confidence desc, rank 1 = most likely)
    └── action_plan: list[ActionPlanItem]
                      └── verification_steps: list[VerificationStep]
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# --------------------------------------------------------------------------- #
# Literal types
# --------------------------------------------------------------------------- #

RiskLevel = Literal["low", "medium", "high"]
EvidenceKind = Literal["metric", "log", "resource", "alert"]
EvidenceSource = Literal["prometheus", "loki", "k8s", "alert", "other"]


# --------------------------------------------------------------------------- #
# EvidenceItem
# --------------------------------------------------------------------------- #


class EvidenceItem(BaseModel):
    """
    A single normalized piece of evidence collected during investigation.

    Fields:
        source: which system the evidence came from
        kind:   the nature of the data (metric value, log line, k8s resource, alert)
        label:  short human-readable identifier, e.g. "restart_count", "oom_events"
        value:  the observed value as a formatted string
        raw:    optional original payload (not stored in DB)
    """

    source: EvidenceSource
    kind: EvidenceKind
    label: str = Field(max_length=100)
    value: str = Field(max_length=500)
    raw: Optional[dict] = Field(default=None, exclude=True)


# --------------------------------------------------------------------------- #
# Hypothesis
# --------------------------------------------------------------------------- #


class Hypothesis(BaseModel):
    """
    A possible root cause hypothesis.

    Hypotheses are ranked by confidence (rank 1 = most likely).
    The analyzer MUST produce at least 2 hypotheses; when the top hypothesis
    confidence is < 0.65 (ambiguous evidence), at least 3 are required.

    Fields:
        title:               short label, e.g. "OOM kill due to memory leak"
        description:         full explanation grounded in the evidence
        confidence:          float [0, 1] — probability this is the true cause
        supporting_evidence: labels of EvidenceItem objects that support this
        rank:                1-based position after confidence-descending sort
    """

    title: str = Field(max_length=200)
    description: str = Field(max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)
    rank: int = Field(ge=1)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, round(float(v), 4)))


# --------------------------------------------------------------------------- #
# VerificationStep
# --------------------------------------------------------------------------- #


class VerificationStep(BaseModel):
    """
    A concrete check to run after an action is applied.

    Fields:
        description: human-readable explanation of what to verify
        check:       a machine-readable expression, e.g. "restart_rate_5m == 0"
                     or "ready_replicas == desired_replicas"
    """

    description: str = Field(max_length=200)
    check: str = Field(max_length=200)


# --------------------------------------------------------------------------- #
# ActionPlanItem
# --------------------------------------------------------------------------- #


class ActionPlanItem(BaseModel):
    """
    A proposed remediation action with risk classification.

    Fields:
        action_id:          must match an id in ALLOWED_ACTIONS
        name:               human-readable name
        description:        why this action addresses the root cause
        risk_level:         low | medium | high
        requires_approval:  whether operator sign-off is needed before execution
        verification_steps: health checks to run after the action completes
        parameters:         key/value pairs to pass to the playbook or runner
    """

    action_id: str
    name: str = Field(max_length=100)
    description: str = Field(max_length=500)
    risk_level: RiskLevel = "medium"
    requires_approval: bool = True
    verification_steps: list[VerificationStep] = Field(default_factory=list)
    parameters: dict = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# StructuredAnalysis
# --------------------------------------------------------------------------- #


class StructuredAnalysis(BaseModel):
    """
    The complete structured output of one analysis run.

    This replaces the previous flat narrative fields with typed, machine-readable
    objects. The flat fields (summary, probable_cause, etc.) are still present in
    AnalysisResponse for backward compatibility — this object carries the richer
    structured data alongside them.

    Fields:
        incident_summary:    concise plain-English description of what happened
        evidence:            normalized evidence items collected by the agent
        hypotheses:          ranked list (rank 1 = most likely), confidence-sorted
        action_plan:         recommended actions with risk and verification steps
        recommended_action_id: top action id (mirrors the flat field)
        overall_confidence:  0–1 score for the overall analysis certainty
        escalate:            true when the situation needs immediate human attention
    """

    incident_summary: str = Field(max_length=1000)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    action_plan: list[ActionPlanItem] = Field(default_factory=list)
    recommended_action_id: Optional[str] = None
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    escalate: bool = False

    @field_validator("overall_confidence", mode="before")
    @classmethod
    def clamp_overall(cls, v: float) -> float:
        return max(0.0, min(1.0, round(float(v), 4)))
