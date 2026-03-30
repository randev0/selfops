import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    AlertEvent,
    AnalysisResult,
    AuditLog,
    Incident,
    IncidentEvidence,
    IncidentStatus,
    RemediationAction,
    SeverityLevel,
)

log = structlog.get_logger()

router = APIRouter()


class IncidentPatch(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None


def _incident_to_dict(incident: Incident) -> dict:
    return {
        "id": str(incident.id),
        "title": incident.title,
        "status": incident.status.value if incident.status else None,
        "severity": incident.severity.value if incident.severity else None,
        "service_name": incident.service_name,
        "namespace": incident.namespace,
        "environment": incident.environment,
        "fingerprint": incident.fingerprint,
        "first_seen_at": incident.first_seen_at.isoformat() if incident.first_seen_at else None,
        "last_seen_at": incident.last_seen_at.isoformat() if incident.last_seen_at else None,
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "updated_at": incident.updated_at.isoformat() if incident.updated_at else None,
    }


def _alert_event_to_dict(ae: AlertEvent) -> dict:
    return {
        "id": str(ae.id),
        "alert_name": ae.alert_name,
        "fingerprint": ae.fingerprint,
        "labels": ae.labels,
        "annotations": ae.annotations,
        "starts_at": ae.starts_at.isoformat() if ae.starts_at else None,
        "ends_at": ae.ends_at.isoformat() if ae.ends_at else None,
        "created_at": ae.created_at.isoformat() if ae.created_at else None,
    }


def _evidence_to_dict(ev: IncidentEvidence) -> dict:
    return {
        "id": str(ev.id),
        "evidence_type": ev.evidence_type,
        "content": ev.content,
        "captured_at": ev.captured_at.isoformat() if ev.captured_at else None,
    }


def _analysis_to_dict(ar: AnalysisResult) -> dict:
    return {
        "id": str(ar.id),
        "model_provider": ar.model_provider,
        "model_name": ar.model_name,
        "prompt_version": ar.prompt_version,
        "summary": ar.summary,
        "probable_cause": ar.probable_cause,
        "recommendation": ar.recommendation,
        "recommended_action_id": ar.recommended_action_id,
        "confidence_score": ar.confidence_score,
        "escalate": ar.escalate,
        "investigation_log": ar.investigation_log,
        "structured_analysis": ar.structured_analysis,
        "created_at": ar.created_at.isoformat() if ar.created_at else None,
    }


def _action_to_dict(ra: RemediationAction) -> dict:
    return {
        "id": str(ra.id),
        "action_type": ra.action_type,
        "action_name": ra.action_name,
        "requested_by": ra.requested_by,
        "execution_mode": ra.execution_mode.value if ra.execution_mode else None,
        "status": ra.status.value if ra.status else None,
        "parameters": ra.parameters,
        "started_at": ra.started_at.isoformat() if ra.started_at else None,
        "completed_at": ra.completed_at.isoformat() if ra.completed_at else None,
        "result_summary": ra.result_summary,
        "remediation_strategy": ra.remediation_strategy,
        "pr_url": ra.pr_url,
        "pr_number": ra.pr_number,
        "pr_branch": ra.pr_branch,
        "patch_file_path": ra.patch_file_path,
        "created_at": ra.created_at.isoformat() if ra.created_at else None,
    }


def _audit_to_dict(al: AuditLog) -> dict:
    return {
        "id": str(al.id),
        "actor_type": al.actor_type,
        "actor_id": al.actor_id,
        "event_type": al.event_type,
        "message": al.message,
        "metadata": al.extra_metadata,
        "created_at": al.created_at.isoformat() if al.created_at else None,
    }


@router.get("")
async def list_incidents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Incident)
        .order_by(Incident.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    incidents = result.scalars().all()
    return [_incident_to_dict(i) for i in incidents]


@router.get("/{incident_id}")
async def get_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
):
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

    data = _incident_to_dict(incident)
    data["alert_events"] = [_alert_event_to_dict(ae) for ae in incident.alert_events]
    data["evidence"] = [_evidence_to_dict(ev) for ev in incident.evidence]
    data["analysis_results"] = [_analysis_to_dict(ar) for ar in incident.analysis_results]
    data["remediation_actions"] = [_action_to_dict(ra) for ra in incident.remediation_actions]
    data["audit_logs"] = [_audit_to_dict(al) for al in incident.audit_logs]
    return data


@router.patch("/{incident_id}")
async def patch_incident(
    incident_id: str,
    body: IncidentPatch,
    db: AsyncSession = Depends(get_db),
):
    try:
        inc_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident ID format")

    result = await db.execute(select(Incident).where(Incident.id == inc_uuid))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    now = datetime.now(timezone.utc)

    if body.status is not None:
        try:
            incident.status = IncidentStatus(body.status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status value: {body.status}",
            )
        if body.status in ("RESOLVED", "CLOSED") and incident.resolved_at is None:
            incident.resolved_at = now

    if body.severity is not None:
        try:
            incident.severity = SeverityLevel(body.severity)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid severity value: {body.severity}",
            )

    incident.updated_at = now

    # Write audit log
    audit_entry = AuditLog(
        id=uuid.uuid4(),
        incident_id=incident.id,
        actor_type="user",
        actor_id="operator",
        event_type="incident.updated",
        message=f"Incident updated: status={body.status}, severity={body.severity}",
        metadata={"status": body.status, "severity": body.severity},
        created_at=now,
    )
    db.add(audit_entry)
    await db.commit()
    await db.refresh(incident)

    return _incident_to_dict(incident)
