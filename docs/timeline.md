# Incident Timeline Aggregator

## Overview

The timeline aggregator builds a normalised, chronologically sorted list of
`TimelineEvent` objects for each incident by merging data from all five
incident-related tables.  No additional database table or migration is
required — the timeline is computed in-memory on every request.

---

## API Endpoint

```
GET /api/incidents/{incident_id}/timeline
```

Returns a JSON array of `TimelineEvent` objects sorted oldest-first.
Returns `404` if the incident does not exist, `400` for a malformed UUID.

### Example response

```json
[
  {
    "id": "alert-fired-3fa85f64-...",
    "incident_id": "6ba7b810-...",
    "timestamp": "2025-01-15T03:12:00+00:00",
    "event_type": "alert.fired",
    "source": "alert",
    "title": "Alert fired: PodCrashLooping",
    "description": "Pod payment-worker is restarting frequently",
    "severity": "critical",
    "metadata": {
      "source_id": "3fa85f64-...",
      "alert_name": "PodCrashLooping",
      "labels": { "severity": "critical", "namespace": "platform" }
    }
  },
  {
    "id": "evidence-7c9e6679-...",
    "incident_id": "6ba7b810-...",
    "timestamp": "2025-01-15T03:13:04+00:00",
    "event_type": "evidence.collected",
    "source": "evidence",
    "title": "Metrics collected",
    "description": "Prometheus metrics snapshot",
    "severity": null,
    "metadata": { "source_id": "7c9e6679-...", "evidence_type": "metric" }
  }
]
```

---

## `TimelineEvent` Shape

| Field        | Type                                               | Description                                      |
|--------------|----------------------------------------------------|--------------------------------------------------|
| `id`         | `string`                                           | Unique event ID (constructed as `<source>-<phase>-<db-uuid>`) |
| `incident_id`| `string`                                           | Parent incident UUID                             |
| `timestamp`  | `string` (ISO 8601)                               | When the event occurred                          |
| `event_type` | `string`                                           | Fine-grained type (see table below)              |
| `source`     | `alert \| evidence \| analysis \| action \| audit` | Which system produced this event                 |
| `title`      | `string`                                           | Short one-line label                             |
| `description`| `string`                                           | Human-readable explanation                       |
| `severity`   | `string \| null`                                   | Alert severity when available, otherwise `null`  |
| `metadata`   | `object`                                           | Source-specific key/value pairs                  |

### `event_type` values

| `source`   | `event_type`         | Trigger                                          |
|------------|----------------------|--------------------------------------------------|
| `alert`    | `alert.fired`        | Alert `starts_at` (or `created_at` fallback)     |
| `alert`    | `alert.resolved`     | Alert `ends_at`                                  |
| `evidence` | `evidence.collected` | `IncidentEvidence.captured_at`                   |
| `analysis` | `analysis.completed` | `AnalysisResult.created_at`                      |
| `action`   | `action.requested`   | `RemediationAction.created_at`                   |
| `action`   | `action.started`     | `RemediationAction.started_at`                   |
| `action`   | `action.completed`   | `RemediationAction.completed_at` (status SUCCESS)|
| `action`   | `action.failed`      | `RemediationAction.completed_at` (status FAILED) |
| `audit`    | *(passthrough)*      | `AuditLog.event_type` (all non-covered types)    |

`AuditLog` events whose `event_type` is already represented by a primary
source (`action.*`, `analysis.completed`, `alert.fired`, etc.) are
suppressed to avoid duplicates.

---

## Sources & Deduplication

Events are merged from all five tables in a single pass.  Each event ID is
constructed as `<source-prefix>-<phase>-<db-uuid>` — for example
`alert-fired-3fa85f64-…` — which is globally unique within an incident.
A `seen` set removes any accidental duplicates before the final sort.

---

## Extensibility

To add a new source (deploy events, trace anomalies, code changes, DB
diagnostics):

1. Write a converter function `_from_<source>(incident_id, row) -> list[TimelineEvent]`
   in `services/api/app/timeline/aggregator.py`, following the existing
   pattern.
2. Load the rows and call the converter inside `build_timeline`.
3. Add the new `source` literal to `TimelineSource` in
   `services/api/app/timeline/models.py`.
4. Add TypeScript handling in `services/frontend/lib/api.ts` if the new
   source needs a distinct visual style in the timeline component.

No API contract changes are required — the `source` field and `event_type`
are open strings from the consumer's perspective.

---

## Files

| File | Role |
|------|------|
| `services/api/app/timeline/__init__.py` | Package marker |
| `services/api/app/timeline/models.py` | `TimelineEvent` Pydantic model |
| `services/api/app/timeline/aggregator.py` | `build_timeline()` + per-source converters |
| `services/api/app/routers/timeline.py` | `GET /{incident_id}/timeline` FastAPI router |
| `services/api/app/main.py` | Registers the timeline router |
| `services/frontend/lib/api.ts` | `ApiTimelineEvent` type + `getTimeline()` |
| `services/frontend/app/incidents/[id]/page.tsx` | Fetches and renders real timeline |
| `tests/api/test_timeline_aggregator.py` | 50+ unit tests for the aggregator |
