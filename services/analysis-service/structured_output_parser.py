"""
structured_output_parser.py
----------------------------
Converts a raw LLM JSON dict into a validated StructuredAnalysis object.

Accepts two input formats:

  v3 (preferred):
    The dict contains ``hypotheses``, ``evidence``, and ``action_plan`` keys
    produced by the updated ReAct prompt.

  v2 / legacy fallback:
    The dict contains only flat fields (probable_cause, evidence_points,
    recommended_action_id, confidence, escalate).  A minimal StructuredAnalysis
    is synthesized from those fields.

Guarantees:
  - Always returns a valid StructuredAnalysis; never raises.
  - Hypotheses list is always non-empty.
  - Every hypothesis has a valid category (symptom | trigger | root_cause).
  - Hypotheses are sorted by confidence descending (rank 1 = most likely).
  - When the top hypothesis confidence is < 0.65 (ambiguous evidence), at least
    3 hypotheses are returned, padded with generic low-confidence candidates.
  - Every ActionPlanItem has risk_level and verification_steps populated —
    defaults are injected per action_id if the LLM omits them.
  - Pre-analyzed EvidenceItems (from deploy/DB data) are merged with LLM evidence.
"""

from __future__ import annotations

import structlog

from domain.models import (
    ActionPlanItem,
    EvidenceItem,
    EvidenceSource,
    EvidenceKind,
    Hypothesis,
    HypothesisCategory,
    RiskLevel,
    StructuredAnalysis,
    VerificationStep,
)

log = structlog.get_logger()

# --------------------------------------------------------------------------- #
# Per-action defaults (risk + approval + verification)
# --------------------------------------------------------------------------- #

_ACTION_DEFAULTS: dict[str, dict] = {
    "restart_deployment": {
        "risk_level": "low",
        "requires_approval": True,
        "verification_steps": [
            VerificationStep(
                description="Restart rate returns to zero",
                check="restart_rate_5m == 0",
            ),
            VerificationStep(
                description="All replicas are ready",
                check="ready_replicas == desired_replicas",
            ),
        ],
    },
    "rollout_restart": {
        "risk_level": "low",
        "requires_approval": True,
        "verification_steps": [
            VerificationStep(
                description="Rollout completes without failures",
                check="rollout_status == complete",
            ),
            VerificationStep(
                description="Zero new OOMKill events in 5 minutes",
                check="oomkill_count_5m == 0",
            ),
        ],
    },
    "scale_up": {
        "risk_level": "medium",
        "requires_approval": True,
        "verification_steps": [
            VerificationStep(
                description="New replicas become ready",
                check="ready_replicas > previous_replicas",
            ),
            VerificationStep(
                description="CPU usage drops below 70%",
                check="cpu_usage_avg < 0.70",
            ),
        ],
    },
}

_GENERIC_VERIFICATION = [
    VerificationStep(
        description="Service returns healthy responses",
        check="health_endpoint == 200",
    ),
    VerificationStep(
        description="Error rate below 1%",
        check="error_rate_5m < 0.01",
    ),
]

# Fallback hypotheses injected when evidence is ambiguous and fewer than 3
# hypotheses were produced.  Tuple: (title, description, confidence, category)
_FALLBACK_HYPOTHESES: list[tuple[str, str, float, HypothesisCategory]] = [
    (
        "Transient infrastructure failure",
        "Temporary resource exhaustion or network blip unrelated to recent code changes.",
        0.20,
        "symptom",
    ),
    (
        "Configuration drift",
        "A recent configuration change introduced unexpected behavior.",
        0.15,
        "trigger",
    ),
    (
        "Resource limits too restrictive",
        "Memory or CPU limits are set too low for the current workload.",
        0.10,
        "root_cause",
    ),
    (
        "Cascading dependency failure",
        "An upstream service or database is causing the observed symptoms.",
        0.10,
        "root_cause",
    ),
]

_VALID_SOURCES: frozenset[EvidenceSource] = frozenset(
    ("prometheus", "loki", "k8s", "alert", "deploy", "database", "other")
)
_VALID_KINDS: frozenset[EvidenceKind] = frozenset(("metric", "log", "resource", "alert"))
_VALID_RISKS: frozenset[RiskLevel] = frozenset(("low", "medium", "high"))
_VALID_CATEGORIES: frozenset[HypothesisCategory] = frozenset(
    ("symptom", "trigger", "root_cause")
)

# ---------------------------------------------------------------------------
# Category inference — keyword-based heuristic used when the LLM does not
# provide a category or provides an invalid one.
# ---------------------------------------------------------------------------

# Keywords that strongly indicate each category (matched as substrings,
# case-insensitive).
_TRIGGER_KEYWORDS: frozenset[str] = frozenset({
    "deploy", "release", "rollout", "migration", "push", "update",
    "config change", "configuration change", "scaling event", "upgrade",
    "new version", "recent change", "just deployed", "just released",
})
_SYMPTOM_KEYWORDS: frozenset[str] = frozenset({
    "saturation", "exhaustion", "high cpu", "high memory", "oom",
    "error rate", "elevated", "latency", "timeout", "pod restart",
    "crash", "crash loop", "connection limit", "rate limiting",
    "response time", "slow", "degraded", "service unavailable",
    "high load", "throttling", "spike", "peak", "overload",
})
_ROOT_CAUSE_KEYWORDS: frozenset[str] = frozenset({
    "leak", "connection pool", "misconfiguration", "bug", "race condition",
    "deadlock", "logic error", "infinite loop", "inefficient query",
    "missing index", "resource limit", "too restrictive", "hard coded",
    "incorrect setting", "wrong configuration", "code defect",
    "memory growth", "unclosed", "not released", "not returned",
})


def _infer_category(title: str, description: str) -> HypothesisCategory:
    """
    Infer a hypothesis category from its title and description when the LLM
    did not provide one.

    Returns "root_cause" as the safest default when no keywords match.
    """
    text = (title + " " + description).lower()

    trigger_score = sum(1 for kw in _TRIGGER_KEYWORDS if kw in text)
    symptom_score = sum(1 for kw in _SYMPTOM_KEYWORDS if kw in text)
    root_cause_score = sum(1 for kw in _ROOT_CAUSE_KEYWORDS if kw in text)

    if trigger_score == 0 and symptom_score == 0 and root_cause_score == 0:
        return "root_cause"

    scores: dict[HypothesisCategory, int] = {
        "trigger": trigger_score,
        "symptom": symptom_score,
        "root_cause": root_cause_score,
    }
    return max(scores, key=scores.__getitem__)  # type: ignore[return-value]

# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _default_steps(action_id: str) -> list[VerificationStep]:
    return list(
        _ACTION_DEFAULTS.get(action_id, {}).get("verification_steps", _GENERIC_VERIFICATION)
    )


def _default_risk(action_id: str) -> RiskLevel:
    return _ACTION_DEFAULTS.get(action_id, {}).get("risk_level", "medium")  # type: ignore[return-value]


def _default_approval(action_id: str) -> bool:
    return _ACTION_DEFAULTS.get(action_id, {}).get("requires_approval", True)


def _parse_evidence(raw_list: list) -> list[EvidenceItem]:
    result: list[EvidenceItem] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        source = item.get("source", "other")
        kind = item.get("kind", "metric")
        result.append(
            EvidenceItem(
                source=source if source in _VALID_SOURCES else "other",
                kind=kind if kind in _VALID_KINDS else "metric",
                label=str(item.get("label", ""))[:100],
                value=str(item.get("value", ""))[:500],
            )
        )
    return result


def _parse_hypotheses(raw_list: list) -> list[Hypothesis]:
    result: list[Hypothesis] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        try:
            title = str(item.get("title", "Unknown"))[:200]
            description = str(item.get("description", ""))[:500]

            # Validate or infer category
            raw_cat = item.get("category")
            if raw_cat in _VALID_CATEGORIES:
                category: HypothesisCategory = raw_cat  # type: ignore[assignment]
            else:
                category = _infer_category(title, description)

            result.append(
                Hypothesis(
                    title=title,
                    description=description,
                    category=category,
                    reasoning_summary=str(item.get("reasoning_summary", ""))[:500],
                    confidence=float(item.get("confidence", 0.5)),
                    supporting_evidence=[
                        str(e)[:200] for e in item.get("supporting_evidence", [])
                    ],
                    rank=1,  # reassigned by _rank()
                )
            )
        except Exception:
            continue
    return result


def _parse_verification_steps(raw_list: list, action_id: str) -> list[VerificationStep]:
    if not isinstance(raw_list, list) or not raw_list:
        return _default_steps(action_id)
    steps: list[VerificationStep] = []
    for s in raw_list:
        if not isinstance(s, dict):
            continue
        steps.append(
            VerificationStep(
                description=str(s.get("description", ""))[:200],
                check=str(s.get("check", ""))[:200],
            )
        )
    return steps or _default_steps(action_id)


def _parse_action_plan(raw_list: list) -> list[ActionPlanItem]:
    result: list[ActionPlanItem] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("action_id", "unknown"))
        risk_raw = item.get("risk_level", _default_risk(action_id))
        risk: RiskLevel = risk_raw if risk_raw in _VALID_RISKS else "medium"  # type: ignore[assignment]
        steps = _parse_verification_steps(item.get("verification_steps", []), action_id)
        try:
            result.append(
                ActionPlanItem(
                    action_id=action_id,
                    name=str(item.get("name", action_id))[:100],
                    description=str(item.get("description", ""))[:500],
                    risk_level=risk,
                    requires_approval=bool(
                        item.get("requires_approval", _default_approval(action_id))
                    ),
                    verification_steps=steps,
                    parameters=(
                        item["parameters"]
                        if isinstance(item.get("parameters"), dict)
                        else {}
                    ),
                )
            )
        except Exception:
            continue
    return result


def _rank(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Sort by confidence descending and assign sequential rank values (1-based)."""
    ordered = sorted(hypotheses, key=lambda h: h.confidence, reverse=True)
    return [h.model_copy(update={"rank": i + 1}) for i, h in enumerate(ordered)]


def _pad_to_three(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """
    When evidence is ambiguous (top confidence < 0.65), ensure at least 3
    hypotheses by appending generic low-confidence candidates.
    Fallback hypotheses include pre-assigned categories.
    """
    if not hypotheses:
        return hypotheses
    if max(h.confidence for h in hypotheses) >= 0.65 or len(hypotheses) >= 3:
        return hypotheses

    existing_lower = {h.title.lower() for h in hypotheses}
    result = list(hypotheses)
    for title, desc, conf, cat in _FALLBACK_HYPOTHESES:
        if len(result) >= 3:
            break
        if title.lower() not in existing_lower:
            result.append(
                Hypothesis(
                    title=title,
                    description=desc,
                    category=cat,
                    reasoning_summary="",
                    confidence=conf,
                    supporting_evidence=[],
                    rank=len(result) + 1,
                )
            )
    return result


def _action_from_id(action_id: str) -> ActionPlanItem:
    """Minimal ActionPlanItem when only the action_id is known."""
    _names = {
        "restart_deployment": "Restart Deployment",
        "rollout_restart": "Rollout Restart",
        "scale_up": "Scale Up Replicas",
    }
    return ActionPlanItem(
        action_id=action_id,
        name=_names.get(action_id, action_id),
        description=f"Apply {action_id} to address the root cause.",
        risk_level=_default_risk(action_id),
        requires_approval=_default_approval(action_id),
        verification_steps=_default_steps(action_id),
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def parse(
    parsed_llm: dict,
    pre_evidence: list[EvidenceItem] | None = None,
    pre_hypotheses: list[Hypothesis] | None = None,
) -> StructuredAnalysis:
    """
    Parse a raw LLM JSON dict into a StructuredAnalysis.

    Accepts both v3 (hypotheses/evidence/action_plan keys present) and v2
    (flat fields only).  Always returns a valid object; never raises.

    Parameters
    ----------
    parsed_llm:
        Raw JSON dict from the LLM output.
    pre_evidence:
        EvidenceItem objects derived from deploy-correlation and database-
        diagnostics data *before* the LLM ran.  These are merged into
        StructuredAnalysis.evidence so the caller has a single combined list.
    pre_hypotheses:
        Hypothesis objects produced by the deterministic hypothesis_classifier
        *before* the LLM ran.  These are merged with the LLM-produced
        hypotheses and deduplicated by title before final ranking.
        Pre-classified hypotheses take precedence on title collisions.
    """
    try:
        return _parse_inner(parsed_llm, pre_evidence or [], pre_hypotheses or [])
    except Exception as exc:
        log.warning(
            "structured_output_parser.parse failed — using minimal fallback",
            error=str(exc),
        )
        return StructuredAnalysis(
            incident_summary=str(parsed_llm.get("summary", "Analysis unavailable"))[:500],
            evidence=list(pre_evidence or []),
            hypotheses=_rank(
                list(pre_hypotheses or [])
                or [
                    Hypothesis(
                        title="Unknown",
                        description="Parser error — manual investigation required.",
                        category="root_cause",
                        confidence=0.0,
                        rank=1,
                    )
                ]
            ),
            overall_confidence=0.0,
            escalate=True,
        )


def _merge_hypotheses(
    pre: list[Hypothesis],
    llm: list[Hypothesis],
) -> list[Hypothesis]:
    """
    Merge deterministic (pre) and LLM-produced hypotheses.

    Strategy:
    - Pre-classified hypotheses take priority on title collisions (they are
      grounded in concrete evidence and are more reliable).
    - LLM hypotheses whose titles do not duplicate a pre-classified one are
      appended.
    - Deduplication is case-insensitive on the first 60 chars of the title.
    """
    seen: set[str] = {h.title.lower()[:60] for h in pre}
    merged = list(pre)
    for h in llm:
        key = h.title.lower()[:60]
        if key not in seen:
            seen.add(key)
            merged.append(h)
    return merged


def _parse_inner(
    flat: dict,
    pre_evidence: list[EvidenceItem] | None = None,
    pre_hypotheses: list[Hypothesis] | None = None,
) -> StructuredAnalysis:
    # ---- Evidence ----
    evidence = _parse_evidence(flat.get("evidence", []))
    if not evidence:
        # v2 fallback: synthesize from evidence_points strings
        evidence = [
            EvidenceItem(
                source="other",
                kind="alert",
                label=str(ep)[:100],
                value=str(ep)[:500],
            )
            for ep in flat.get("evidence_points", [])
        ]

    # ---- Hypotheses ----
    llm_hypotheses = _parse_hypotheses(flat.get("hypotheses", []))
    if not llm_hypotheses:
        # v2 fallback: one hypothesis from probable_cause
        probable_cause = flat.get("probable_cause", "Unknown cause")
        llm_hypotheses = [
            Hypothesis(
                title=str(probable_cause)[:200],
                description=str(probable_cause)[:500],
                confidence=float(flat.get("confidence", 0.5)),
                supporting_evidence=flat.get("evidence_points", []),
                rank=1,
            )
        ]

    # Merge deterministic pre-classified hypotheses with LLM-produced ones.
    # Pre-classified hypotheses win on title collision.
    hypotheses = _merge_hypotheses(list(pre_hypotheses or []), llm_hypotheses)

    hypotheses = _pad_to_three(hypotheses)
    hypotheses = _rank(hypotheses)

    # ---- Action plan ----
    action_plan = _parse_action_plan(flat.get("action_plan", []))
    recommended_id = flat.get("recommended_action_id")
    if not action_plan and recommended_id:
        action_plan = [_action_from_id(recommended_id)]

    return StructuredAnalysis(
        incident_summary=str(flat.get("summary", ""))[:1000],
        evidence=list(pre_evidence or []) + evidence,
        hypotheses=hypotheses,
        action_plan=action_plan,
        recommended_action_id=recommended_id,
        overall_confidence=float(flat.get("confidence", 0.0)),
        escalate=bool(flat.get("escalate", False)),
    )
