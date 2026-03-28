import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Incident
from app.timeline.aggregator import build_timeline

log = structlog.get_logger()
router = APIRouter()


@router.get("/{incident_id}/timeline")
async def get_incident_timeline(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Return a normalised, chronologically sorted timeline for an incident,
    merging events from all five source tables:
    AlertEvent, IncidentEvidence, AnalysisResult, RemediationAction, AuditLog.
    """
    try:
        inc_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident ID format")

    result = await db.execute(
        select(Incident)
        .options(
            selectinload(Incident.alert_events),
            selectinload(Incident.evidence),
            selectinload(Incident.analysis_results),
            selectinload(Incident.remediation_actions),
            selectinload(Incident.audit_logs),
        )
        .where(Incident.id == inc_uuid)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    events = build_timeline(
        incident_id=inc_uuid,
        alert_events=incident.alert_events,
        evidence=incident.evidence,
        analysis_results=incident.analysis_results,
        remediation_actions=incident.remediation_actions,
        audit_logs=incident.audit_logs,
    )

    return [e.model_dump() for e in events]
