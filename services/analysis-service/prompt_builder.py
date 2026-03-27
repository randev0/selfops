import json
from schemas import AnalysisRequest


def build_prompt(request: AnalysisRequest) -> str:
    alert_labels_formatted = json.dumps(request.alert_labels, indent=2)
    alert_annotations_formatted = json.dumps(request.alert_annotations, indent=2)
    actions_formatted = "\n".join(
        f"  - action_id: {a.get('action_id', 'unknown')}\n"
        f"    name: {a.get('name', 'unknown')}\n"
        f"    description: {a.get('description', '')}"
        for a in request.allowed_actions
    ) or "  No actions available"

    return f"""You are an expert Site Reliability Engineer analyzing a Kubernetes infrastructure incident.
Your job is to produce a concise, accurate incident analysis based on the provided evidence.
Be factual and specific. Do not speculate beyond the evidence.

INCIDENT TITLE: {request.incident_title}
SERVICE: {request.service_name or 'unknown'} | NAMESPACE: {request.namespace or 'unknown'}
ALERT: {request.alert_name}
ALERT LABELS: {alert_labels_formatted}
ALERT ANNOTATIONS: {alert_annotations_formatted}

RECENT METRICS (last 5 minutes):
{request.metrics_summary or "No metrics available"}

RELEVANT LOG LINES:
{request.log_lines or "No logs available"}

AVAILABLE REMEDIATION ACTIONS:
{actions_formatted}

Respond with a JSON object containing exactly these fields:
{{
  "summary": "2-3 sentence plain English description of what happened",
  "probable_cause": "The most likely root cause based on the evidence",
  "evidence_points": ["key evidence 1", "key evidence 2", "key evidence 3"],
  "recommended_action_id": "the action_id from the available actions, or null if none apply",
  "confidence": 0.0 to 1.0,
  "escalate": true if the situation needs immediate human attention, false otherwise
}}
Respond only with the JSON object. No markdown, no explanation, no code blocks."""
