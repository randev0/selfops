from pydantic import BaseModel
from typing import Optional, List


class AnalysisRequest(BaseModel):
    incident_id: str
    incident_title: str
    service_name: Optional[str] = None
    namespace: Optional[str] = None
    alert_name: str
    alert_labels: dict
    alert_annotations: dict
    metrics_summary: Optional[str] = None
    log_lines: Optional[str] = None
    allowed_actions: List[dict]


class AnalysisResponse(BaseModel):
    summary: str
    probable_cause: str
    evidence_points: List[str]
    recommended_action_id: Optional[str] = None
    confidence: float
    escalate: bool
    raw_output: dict
    # ReAct agent thought chain: list of {type, content/tool/input} dicts
    investigation_log: Optional[List[dict]] = None
