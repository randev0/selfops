# Structured Analysis Output (v3)

## Overview

Starting from the `v3-structured` prompt version, the analysis service produces a
fully-typed `StructuredAnalysis` object alongside the legacy flat fields.
This enables downstream consumers (UI, audit tooling, auto-remediation) to
reason about incidents programmatically rather than parsing narrative text.

---

## Output Shape

### `AnalysisResponse` (HTTP response from `/analyze`)

All v2 flat fields are preserved unchanged.  The new `structured` field is
`null` on error paths and on responses from older deployments.

```json
{
  "summary":               "string — 2-3 sentence plain-English description",
  "probable_cause":        "string — root cause (v2 compat)",
  "evidence_points":       ["string", "..."],
  "recommended_action_id": "string | null",
  "confidence":            0.85,
  "escalate":              false,
  "investigation_log":     [{ "type": "thought|action|observation|...", "content": "..." }],

  "structured": {
    "incident_summary":    "string",
    "evidence":            [ EvidenceItem ],
    "hypotheses":          [ Hypothesis ],
    "action_plan":         [ ActionPlanItem ],
    "recommended_action_id": "string | null",
    "overall_confidence":  0.85,
    "escalate":            false
  }
}
```

### `EvidenceItem`

| Field    | Type                                             | Description                          |
|----------|--------------------------------------------------|--------------------------------------|
| `source` | `prometheus \| loki \| k8s \| alert \| other`    | Which system produced this evidence  |
| `kind`   | `metric \| log \| resource \| alert`             | Nature of the data                   |
| `label`  | `string` (max 100 chars)                         | Short identifier, e.g. `restart_count` |
| `value`  | `string` (max 500 chars)                         | Formatted observed value             |

### `Hypothesis`

Ordered by `confidence` descending.  `rank = 1` is the most likely cause.

| Field                | Type               | Description                                      |
|----------------------|--------------------|--------------------------------------------------|
| `title`              | `string` (max 200) | Short label, e.g. "OOM kill due to memory leak"  |
| `description`        | `string` (max 500) | Full explanation grounded in the evidence        |
| `confidence`         | `float` [0, 1]     | Probability this is the true root cause          |
| `supporting_evidence`| `string[]`         | Labels of `EvidenceItem`s that support this      |
| `rank`               | `int` (≥ 1)        | 1-based position after confidence sort           |

**Ambiguity rule:** When the top hypothesis `confidence < 0.65`, the parser
ensures at least 3 hypotheses are present by injecting generic low-confidence
fallback candidates.

### `ActionPlanItem`

| Field               | Type                     | Description                                         |
|---------------------|--------------------------|-----------------------------------------------------|
| `action_id`         | `string`                 | Must match a key in `ALLOWED_ACTIONS`               |
| `name`              | `string` (max 100)       | Human-readable name                                 |
| `description`       | `string` (max 500)       | Why this action addresses the root cause            |
| `risk_level`        | `low \| medium \| high`  | Risk classification                                 |
| `requires_approval` | `bool`                   | Whether operator sign-off is required               |
| `verification_steps`| `VerificationStep[]`     | Health checks to run after the action completes     |
| `parameters`        | `dict`                   | Key/value pairs for the playbook or runner          |

### `VerificationStep`

| Field         | Type     | Description                                       |
|---------------|----------|---------------------------------------------------|
| `description` | `string` | Human-readable explanation of what to verify      |
| `check`       | `string` | Machine-readable expression, e.g. `restart_rate_5m == 0` |

---

## Default Risk Levels and Verification Steps

The parser enriches every `ActionPlanItem` with defaults when the LLM omits them:

| `action_id`          | `risk_level` | `requires_approval` | Default verification checks                              |
|----------------------|--------------|---------------------|----------------------------------------------------------|
| `restart_deployment` | `low`        | `true`              | `restart_rate_5m == 0`, `ready_replicas == desired_replicas` |
| `rollout_restart`    | `low`        | `true`              | `rollout_status == complete`, `oomkill_count_5m == 0`    |
| `scale_up`           | `medium`     | `true`              | `ready_replicas > previous_replicas`, `cpu_usage_avg < 0.70` |
| *(unknown)*          | `medium`     | `true`              | `health_endpoint == 200`, `error_rate_5m < 0.01`         |

---

## Database

Migration `002_structured_analysis.sql` adds a nullable `JSONB` column to
`analysis_results`:

```sql
ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS structured_analysis JSONB;
```

Rows written by `v2-react` workers remain valid with `structured_analysis = NULL`.
The `prompt_version` column distinguishes old from new rows:

| `prompt_version` | What it means                                      |
|------------------|----------------------------------------------------|
| `v2-react`       | Old flat output; `structured_analysis` is NULL     |
| `v3-structured`  | New structured output; `structured_analysis` is set |

---

## Files Changed

| File | Change |
|------|--------|
| `services/analysis-service/domain/__init__.py` | **new** — package marker |
| `services/analysis-service/domain/models.py` | **new** — `EvidenceItem`, `Hypothesis`, `VerificationStep`, `ActionPlanItem`, `StructuredAnalysis` |
| `services/analysis-service/structured_output_parser.py` | **new** — parser with v3/v2 fallback, ranking, padding |
| `services/analysis-service/schemas.py` | **modified** — added `structured: Optional[StructuredAnalysis]` to `AnalysisResponse` |
| `services/analysis-service/react_agent.py` | **modified** — extended `_REACT_PROMPT` with `hypotheses`/`evidence`/`action_plan` keys; calls parser after JSON parse |
| `services/api/app/models.py` | **modified** — added `structured_analysis: Optional[dict]` to `AnalysisResult` |
| `services/api/app/routers/incidents.py` | **modified** — `_analysis_to_dict` now includes `structured_analysis` |
| `services/api/migrations/002_structured_analysis.sql` | **new** — adds column + indexes |
| `services/worker/worker.py` | **modified** — inline `AnalysisResult` model updated; worker stores `structured_analysis`; sets `prompt_version = "v3-structured"` when present; derives `recommendation` from `action_plan[0].description` |
| `services/frontend/lib/api.ts` | **modified** — added `StructuredAnalysis` and related interfaces; `Analysis.structured_analysis` field |
| `tests/analysis-service/` | **new** — 61 pytest tests across 4 files |
| `docs/structured-analysis.md` | **new** — this file |

---

## Migration / Compatibility Notes

1. **No breaking changes to existing API consumers.**  All v2 flat fields
   (`summary`, `probable_cause`, `evidence_points`, `confidence`, `escalate`,
   `investigation_log`, `recommended_action_id`) are still present in
   `AnalysisResponse` and stored in `AnalysisResult`.

2. **`structured_analysis` is nullable.**  Pre-migration rows have `NULL`; code
   reading this field must handle `None`/`null`.  The frontend `Analysis`
   interface declares it as `StructuredAnalysis | null`.

3. **`prompt_version` changed** from `"v2-react"` to `"v3-structured"` for new
   analyses.  Existing data is unaffected.

4. **`recommendation` field improved.**  The worker now falls back to
   `action_plan[0].description` when the analysis service does not return a
   top-level `recommendation` key, so existing Telegram notifications and
   frontend display are improved rather than broken.

5. **LLM output degrades gracefully.**  If the LLM does not include the new
   `hypotheses`/`evidence`/`action_plan` keys (e.g. for a long incident context
   that forces truncation), the parser silently synthesises `StructuredAnalysis`
   from the v2 flat fields.  The `structured` field is always non-`None` in a
   successful `/analyze` response.

---

## Follow-up Tasks

- **Phase 4 (App Ops Frontend):** Add a "Hypotheses" panel and "Action Plan"
  panel to the incident detail page using `structured_analysis.hypotheses` and
  `structured_analysis.action_plan`.
- **Verification runner:** Wire `verification_steps[].check` into
  `verify_remediation` so automated checks replace the current hardcoded
  metric queries.
- **Trace integration (v2 Phase 2):** Add `get_trace_samples` tool output as
  `EvidenceItem` objects with `source="k8s"`, `kind="log"`.
- **Risk gating:** Enforce `requires_approval = true` in the remediation runner
  as an additional safety gate before executing high-risk actions.
- **Backfill:** Consider a one-time job to re-parse `raw_output` for existing
  `v2-react` rows and populate `structured_analysis` retrospectively.
