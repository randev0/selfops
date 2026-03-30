# Analysis Reasoning — Hypothesis Classification

This document explains how SelfOps classifies incident hypotheses into
**symptom**, **trigger**, and **root_cause** categories, and how the
deterministic classifier combines with the LLM-based ReAct agent.

---

## Hypothesis Categories

Every hypothesis in a `StructuredAnalysis` belongs to exactly one category:

### `symptom`
An **observable effect** visible in monitoring or alerting.

Symptoms are the *starting point* of an investigation — they are what
Prometheus, Loki, or the alert itself is directly measuring.

Examples:
- Database connection pool at 92% saturation
- Pod crash-looping (kube_pod_container_status_restarts_total elevated)
- Elevated CPU utilization triggering HighCPUUsage alert
- Blocked queries in pg_stat_activity

### `trigger`
A **recent change** that preceded the symptom.

Triggers explain *when* and *what changed*, but not *why* the change caused
the problem.

Examples:
- Deploy `v2.5.0` pushed 8 minutes before the alert fired
- Configuration change in the correlation window
- Scaling event that changed the number of replicas

### `root_cause`
The **underlying technical reason** that connects the trigger to the symptom.

Root causes explain *why* the change or condition caused the observed symptom.
They are **hypotheses, not certainties** — SelfOps never claims absolute
certainty about a root cause.

Examples:
- Connection leak introduced by a new code path in the deploy
- Missing database index causing query plans to degrade under load
- Memory limit too restrictive for the current workload
- Pre-existing lock contention not cleaned up by application logic

---

## How Reasoning Works

Analysis uses a **two-layer approach**:

```
Evidence Sources
  ├── deploy_correlation  ──┐
  ├── database_diagnostics ─┤──► deterministic classifier ──► pre-classified hypotheses
  └── alert context ────────┘             │
                                          ▼
                                  structured_output_parser
                                          ▲
  ReAct agent (LLM) ──────────────────────┘
       │
       ├── Prometheus tool calls
       ├── Loki tool calls
       └── k8s resource queries
```

### Layer 1 — Deterministic Classifier (`hypothesis_classifier.py`)

Runs **before** the LLM. Examines structured evidence and applies explicit
rules to produce typed hypotheses.

Because the input is structured (not free text), these hypotheses are
directly grounded in concrete evidence values and are reliable even when the
LLM produces low-quality output.

**Confidence scale for deterministic hypotheses:**

| Signal strength | Confidence |
|-----------------|-----------|
| Multiple corroborating signals (e.g. deploy + long-idle + saturation > 90%) | 0.70–0.90 |
| Two corroborating signals | 0.55–0.70 |
| Single strong signal | 0.40–0.60 |
| Single weak / speculative signal | 0.20–0.40 |
| No supporting evidence | Not produced |

The classifier **never returns 1.0**. Maximum is 0.90 regardless of signal
strength, because root causes are inferences, not observations.

### Layer 2 — LLM ReAct Agent (`react_agent.py`)

The ReAct agent receives:
- The alert title, labels, and annotations
- Pre-formatted deploy correlation and DB diagnostics text blocks
- SOP (Standard Operating Procedure) context from the BM25 retriever
- Available remediation actions

It iterates through tool calls (Prometheus, Loki, k8s) to gather additional
evidence, then produces a structured JSON response that includes hypotheses
with `category`, `reasoning_summary`, and `confidence` fields.

The LLM prompt explicitly instructs the agent to:
1. Classify each hypothesis as `symptom`, `trigger`, or `root_cause`
2. Provide a `reasoning_summary` explaining why the category applies
3. Include at least one hypothesis per category when evidence supports it
4. Use the confidence scale consistently

### Merging

`structured_output_parser.parse()` merges both layers:

1. **Deterministic hypotheses take priority** on title collisions (first 60
   chars, case-insensitive).
2. LLM hypotheses whose titles do not conflict are appended.
3. All hypotheses are sorted by confidence descending (`rank=1` is most
   likely).
4. When the top confidence is below 0.65 and fewer than 3 hypotheses exist,
   generic low-confidence fallback candidates are padded in to signal
   ambiguity.

---

## Rule Summary

The deterministic classifier applies these rules:

### Symptoms produced when:
| Condition | Hypothesis title |
|-----------|-----------------|
| `connection_saturation_pct >= 70%` | Database connection pool saturation |
| `long_idle_connections > 0` AND saturation < 70% | Elevated idle database connections |
| `blocked_queries > 0` | Lock contention causing query blocking |
| Alert name/labels contain crash/OOM/restart keywords | Pod crash loop |
| Alert name/labels contain high-CPU keywords | Elevated CPU utilization |
| Alert name/labels contain high-memory/OOM keywords | Elevated memory consumption |

### Triggers produced when:
| Condition | Hypothesis title |
|-----------|-----------------|
| `deploy_correlation.likely_regression = true` | Recent deploy preceded the incident |
| Deploys present but `likely_regression = false` | Deploy activity in window (weak signal) |

### Root causes inferred from trigger + symptom combinations:
| Condition | Hypothesis title |
|-----------|-----------------|
| Deploy + long_idle_connections | Connection leak introduced by recent deploy |
| Deploy + saturation >= 70% (no long-idle) | Deploy-induced DB saturation (mechanism unclear) |
| Deploy + no DB data | Deploy regression (root cause unknown — no DB data) |
| No deploy + long_idle_connections | Pre-existing connection leak |
| No deploy + blocked_queries | Query lock contention due to misconfiguration or logic error |
| No deploy + saturation >= 70% (no long-idle) | DB saturation from workload growth or under-provisioned limits |
| Crash loop alert + no structured evidence | Application error causing crash loop (cause unknown) |

---

## Output Structure

Every `StructuredAnalysis` response contains:

```json
{
  "incident_summary": "Plain English description of what happened",
  "evidence": [
    {
      "source": "database | deploy | prometheus | loki | k8s | alert | other",
      "kind": "metric | log | resource | alert",
      "label": "short identifier",
      "value": "observed value"
    }
  ],
  "hypotheses": [
    {
      "title": "Short label",
      "description": "Full explanation grounded in evidence",
      "category": "symptom | trigger | root_cause",
      "reasoning_summary": "One sentence explaining why this category applies",
      "confidence": 0.75,
      "supporting_evidence": ["evidence label 1", "evidence label 2"],
      "rank": 1
    }
  ],
  "action_plan": [
    {
      "action_id": "rollout_restart",
      "name": "Rollout Restart",
      "description": "Why this action addresses the root cause",
      "risk_level": "low | medium | high",
      "requires_approval": true,
      "verification_steps": [...]
    }
  ],
  "recommended_action_id": "rollout_restart",
  "overall_confidence": 0.72,
  "escalate": false
}
```

### Hypothesis ranking

Hypotheses are sorted by `confidence` descending. `rank=1` is the most
likely hypothesis. All hypotheses are considered — the top-ranked one is
not necessarily correct, especially when `overall_confidence < 0.65`.

---

## Known Limitations

1. **No distributed tracing.** The classifier cannot detect slow span chains
   or inter-service latency contributions. Adding trace correlation is a
   planned future improvement.

2. **No code-level inspection.** The classifier cannot inspect diffs or
   identify which specific code change introduced a connection leak. It can
   only flag the temporal correlation.

3. **DB diagnostics require the adapter.** If the worker's PostgreSQL
   diagnostics adapter fails or times out, `database_diagnostics` will be
   absent and deterministic DB-based hypotheses will not be produced.

4. **Regression window is fixed.** The `likely_regression` flag is set by
   the GitHub correlation adapter based on a configurable window
   (default: 30 minutes). Slow-burn regressions that manifest hours after
   a deploy will not be flagged.

5. **Alert keyword matching is conservative.** The classifier uses a fixed
   keyword set. Novel alert names that don't match the keywords will fall
   back to LLM-only classification.

6. **Multiple simultaneous incidents.** When multiple alerts fire at once,
   each incident is analyzed independently. Cross-incident correlation
   (e.g., one root cause affecting multiple services) is not yet supported.

---

## Future Improvements

- **Trace correlation adapter**: inject span data to detect inter-service
  latency as a contributing symptom.
- **Code diff analysis**: parse the changed files from the deploy correlation
  to identify connection pool or resource management patterns.
- **Historical baseline**: compare current metrics against a rolling baseline
  to detect gradual drift (workload growth vs. sudden regression).
- **Cross-incident graph**: detect when multiple active incidents share a
  common root cause (e.g., a shared database or upstream service).
