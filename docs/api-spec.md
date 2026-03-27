# SelfOps API Specification

**Base URL:** `http://<server-ip>/api`
**API Docs (Swagger):** `http://<server-ip>/api/docs`
**OpenAPI JSON:** `http://<server-ip>/api/openapi.json`

All responses are JSON. Timestamps are ISO 8601 UTC strings.

---

## Health

### `GET /api/health`
Returns service health status.

**Response 200:**
```json
{
  "status": "ok",
  "service": "selfops-api"
}
```

---

## Alerts

### `POST /api/alerts/webhook`
Receives alert notifications from Alertmanager. Creates or updates incidents.

**Request body (Alertmanager format):**
```json
{
  "version": "4",
  "groupKey": "{}:{alertname=\"PodCrashLooping\"}",
  "status": "firing",
  "receiver": "selfops-webhook",
  "groupLabels": {
    "alertname": "PodCrashLooping"
  },
  "commonLabels": {
    "alertname": "PodCrashLooping",
    "namespace": "platform",
    "severity": "critical"
  },
  "commonAnnotations": {
    "summary": "Pod is crash looping",
    "description": "Pod selfops-demo-app-xxx is restarting frequently"
  },
  "externalURL": "http://alertmanager:9093",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "PodCrashLooping",
        "namespace": "platform",
        "pod": "selfops-demo-app-xxx-yyy",
        "severity": "critical"
      },
      "annotations": {
        "summary": "Pod is crash looping",
        "description": "..."
      },
      "startsAt": "2024-01-01T00:00:00Z",
      "endsAt": "0001-01-01T00:00:00Z",
      "fingerprint": "abc123"
    }
  ]
}
```

**Response 200:**
```json
{
  "processed": 1,
  "incidents_created": 1,
  "incidents_updated": 0
}
```

Note: Always returns 200. Alertmanager retries on non-2xx.

---

## Incidents

### `GET /api/incidents`
List all incidents, ordered by created_at DESC.

**Query parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | integer | 20 | Max results to return (max 100) |
| `offset` | integer | 0 | Pagination offset |
| `status` | string | null | Filter by status |
| `severity` | string | null | Filter by severity |

**Response 200:**
```json
{
  "total": 42,
  "limit": 20,
  "offset": 0,
  "items": [
    {
      "id": "uuid",
      "title": "PodCrashLooping in platform",
      "status": "ACTION_REQUIRED",
      "severity": "critical",
      "service_name": "selfops-demo-app",
      "namespace": "platform",
      "environment": "production",
      "fingerprint": "abc123",
      "first_seen_at": "2024-01-01T00:00:00Z",
      "last_seen_at": "2024-01-01T00:05:00Z",
      "resolved_at": null,
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:05:00Z"
    }
  ]
}
```

---

### `GET /api/incidents/{id}`
Get full incident detail including all related data.

**Path parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `id` | UUID | Incident ID |

**Response 200:**
```json
{
  "id": "uuid",
  "title": "PodCrashLooping in platform",
  "status": "ACTION_REQUIRED",
  "severity": "critical",
  "service_name": "selfops-demo-app",
  "namespace": "platform",
  "environment": "production",
  "fingerprint": "abc123",
  "first_seen_at": "2024-01-01T00:00:00Z",
  "last_seen_at": "2024-01-01T00:05:00Z",
  "resolved_at": null,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:05:00Z",
  "alert_events": [...],
  "evidence": [...],
  "analysis": {...},
  "actions": [...],
  "audit_logs": [...]
}
```

**Response 404:**
```json
{"detail": "Incident not found"}
```

---

### `PATCH /api/incidents/{id}`
Update incident status or severity.

**Request body:**
```json
{
  "status": "CLOSED",
  "severity": "warning"
}
```

All fields optional. Only provided fields are updated.

**Response 200:** Updated incident object (same shape as GET)

---

## Actions

### `GET /api/incidents/{id}/actions`
List all remediation actions for an incident.

**Response 200:**
```json
[
  {
    "id": "uuid",
    "incident_id": "uuid",
    "action_type": "deployment",
    "action_name": "Restart Deployment",
    "requested_by": "operator",
    "execution_mode": "manual",
    "status": "SUCCESS",
    "parameters": {
      "deployment_name": "selfops-demo-app",
      "namespace": "platform"
    },
    "started_at": "2024-01-01T00:10:00Z",
    "completed_at": "2024-01-01T00:11:30Z",
    "result_summary": "Rollout completed successfully",
    "raw_output": {...},
    "created_at": "2024-01-01T00:09:00Z"
  }
]
```

---

### `POST /api/incidents/{id}/actions/{action_id}/run`
Trigger a remediation action for an incident.

**Path parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `id` | UUID | Incident ID |
| `action_id` | string | Action type ID (e.g. "restart_deployment") |

**Request body:**
```json
{
  "parameters": {
    "deployment_name": "selfops-demo-app",
    "namespace": "platform"
  },
  "requested_by": "operator"
}
```

**Response 202:**
```json
{
  "action_id": "uuid",
  "status": "PENDING",
  "message": "Action queued for execution"
}
```

**Response 400:**
```json
{"detail": "Missing required parameter: deployment_name"}
```

**Response 403:**
```json
{"detail": "Namespace 'kube-system' is not allowed for this action"}
```

---

## Audit Logs

### `GET /api/incidents/{id}/audit`
Get the full audit trail for an incident, ordered by created_at DESC.

**Response 200:**
```json
[
  {
    "id": "uuid",
    "incident_id": "uuid",
    "actor_type": "system",
    "actor_id": "worker",
    "event_type": "analysis.completed",
    "message": "LLM analysis completed with confidence 0.87",
    "metadata": {
      "model": "anthropic/claude-3-haiku",
      "confidence": 0.87,
      "recommended_action": "restart_deployment"
    },
    "created_at": "2024-01-01T00:08:00Z"
  }
]
```

---

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Human-readable error description"
}
```

| HTTP Status | Meaning |
|-------------|---------|
| 400 | Bad request (validation error, missing params) |
| 403 | Forbidden (action not allowed for namespace/type) |
| 404 | Resource not found |
| 422 | Unprocessable entity (request body schema violation) |
| 500 | Internal server error |

---

## Analysis Service (Internal)

The analysis service is an internal microservice not exposed through the ingress.

### `POST /analyze`
Accepts enriched incident context and returns LLM analysis.

**Request body:**
```json
{
  "incident_id": "uuid",
  "incident_title": "PodCrashLooping in platform",
  "service_name": "selfops-demo-app",
  "namespace": "platform",
  "alert_name": "PodCrashLooping",
  "alert_labels": {"severity": "critical", "pod": "demo-xxx"},
  "alert_annotations": {"summary": "Pod is crash looping"},
  "metrics_summary": "Pod restart count: 5 in last 5 minutes. CPU: 0.1 cores. Memory: 45MB.",
  "log_lines": "2024-01-01 00:00:01 ERROR: connection refused\n...",
  "allowed_actions": [
    {"action_id": "restart_deployment", "name": "Restart Deployment", "description": "..."}
  ]
}
```

**Response 200:**
```json
{
  "summary": "The selfops-demo-app deployment is crash looping due to a deliberate crash trigger.",
  "probable_cause": "Application received a /crash request which called os._exit(1), causing repeated pod restarts.",
  "evidence_points": [
    "5 restarts in 5 minutes",
    "Log shows deliberate exit: 'crashing...'",
    "No OOM events — pure application-level crash"
  ],
  "recommended_action_id": "restart_deployment",
  "confidence": 0.92,
  "escalate": false,
  "raw_output": {...}
}
```
