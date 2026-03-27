import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import AuditLog, Incident, RemediationAction, ActionStatus, ExecutionMode

log = structlog.get_logger()

router = APIRouter()

ALLOWED_ACTIONS: dict[str, dict] = {
    "restart_deployment": {
        "name": "Restart Deployment",
        "description": "Performs a rollout restart of the specified deployment",
        "playbook": "remediation/restart_deployment.yml",
        "safe_for_auto": False,
        "required_params": ["deployment_name", "namespace"],
        "allowed_namespaces": ["platform"],
    },
    "rollout_restart": {
        "name": "Rollout Restart",
        "description": "Graceful rolling restart that replaces pods one at a time",
        "playbook": "remediation/rollout_restart.yml",
        "safe_for_auto": False,
        "required_params": ["deployment_name", "namespace"],
        "allowed_namespaces": ["platform"],
    },
    "scale_up": {
        "name": "Scale Up Replicas",
        "description": "Increases replica count by 1, up to a maximum of 4",
        "playbook": "remediation/scale_up.yml",
        "safe_for_auto": False,
        "required_params": ["deployment_name", "namespace", "max_replicas"],
        "allowed_namespaces": ["platform"],
    },
}


def _validate_action(action_id: str, params: dict) -> tuple[bool, str]:
    if action_id not in ALLOWED_ACTIONS:
        return False, f"Action '{action_id}' is not in the allowed list"
    action = ALLOWED_ACTIONS[action_id]
    for param in action["required_params"]:
        if param not in params:
            return False, f"Missing required parameter: {param}"
    namespace = params.get("namespace")
    if namespace and namespace not in action["allowed_namespaces"]:
        return False, f"Namespace '{namespace}' is not allowed for this action"
    return True, "ok"


async def _enqueue_job(job_name: str, *args) -> None:
    try:
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        arq_redis = await create_pool(redis_settings)
        await arq_redis.enqueue_job(job_name, *args)
        await arq_redis.aclose()
    except Exception as exc:
        log.error("Failed to enqueue job", job=job_name, error=str(exc))


class RunActionBody(BaseModel):
    parameters: dict[str, Any] = {}
    requested_by: Optional[str] = "operator"


@router.post("/{incident_id}/actions/{action_id}/run")
async def run_action(
    incident_id: str,
    action_id: str,
    body: RunActionBody,
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

    # Validate action
    valid, reason = _validate_action(action_id, body.parameters)
    if not valid:
        raise HTTPException(status_code=400, detail=reason)

    action_def = ALLOWED_ACTIONS[action_id]
    now = datetime.now(timezone.utc)

    # Create remediation_action row
    action = RemediationAction(
        id=uuid.uuid4(),
        incident_id=inc_uuid,
        action_type=action_id,
        action_name=action_def["name"],
        requested_by=body.requested_by or "operator",
        execution_mode=ExecutionMode.manual,
        status=ActionStatus.PENDING,
        parameters=body.parameters,
        created_at=now,
    )
    db.add(action)
    await db.flush()

    # Write audit log
    audit_entry = AuditLog(
        id=uuid.uuid4(),
        incident_id=inc_uuid,
        actor_type="user",
        actor_id=body.requested_by or "operator",
        event_type="action.requested",
        message=f"Action requested by operator: {action_def['name']}",
        metadata={
            "action_id": action_id,
            "action_db_id": str(action.id),
            "parameters": body.parameters,
        },
        created_at=now,
    )
    db.add(audit_entry)
    await db.commit()

    # Enqueue the action execution job
    await _enqueue_job("run_remediation", str(action.id))

    return {"action_id": str(action.id), "status": "PENDING"}


@router.get("/{incident_id}/actions")
async def list_actions(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        inc_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident ID format")

    result = await db.execute(
        select(RemediationAction)
        .where(RemediationAction.incident_id == inc_uuid)
        .order_by(RemediationAction.created_at.desc())
    )
    actions = result.scalars().all()

    return [
        {
            "id": str(a.id),
            "action_type": a.action_type,
            "action_name": a.action_name,
            "requested_by": a.requested_by,
            "execution_mode": a.execution_mode.value if a.execution_mode else None,
            "status": a.status.value if a.status else None,
            "parameters": a.parameters,
            "started_at": a.started_at.isoformat() if a.started_at else None,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            "result_summary": a.result_summary,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in actions
    ]
