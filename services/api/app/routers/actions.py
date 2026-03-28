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


GITOPS_PR = "GITOPS_PR"
DIRECT_ACTION = "DIRECT_ACTION"


class RunActionBody(BaseModel):
    parameters: dict[str, Any] = {}
    requested_by: Optional[str] = "operator"
    strategy: Optional[str] = DIRECT_ACTION  # DIRECT_ACTION | GITOPS_PR


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

    strategy = body.strategy or DIRECT_ACTION
    if strategy not in (DIRECT_ACTION, GITOPS_PR):
        raise HTTPException(status_code=400, detail=f"Unknown strategy '{strategy}'")

    # DIRECT_ACTION requires valid action params; GITOPS_PR validates lazily
    if strategy == DIRECT_ACTION:
        valid, reason = _validate_action(action_id, body.parameters)
        if not valid:
            raise HTTPException(status_code=400, detail=reason)

    action_def = ALLOWED_ACTIONS.get(action_id, {"name": action_id})
    now = datetime.now(timezone.utc)

    action = RemediationAction(
        id=uuid.uuid4(),
        incident_id=inc_uuid,
        action_type=action_id,
        action_name=action_def["name"],
        requested_by=body.requested_by or "operator",
        execution_mode=ExecutionMode.manual,
        status=ActionStatus.PENDING,
        parameters=body.parameters,
        remediation_strategy=strategy,
        created_at=now,
    )
    db.add(action)
    await db.flush()

    audit_entry = AuditLog(
        id=uuid.uuid4(),
        incident_id=inc_uuid,
        actor_type="user",
        actor_id=body.requested_by or "operator",
        event_type="action.requested",
        message=f"[{strategy}] Action requested: {action_def['name']}",
        extra_metadata={
            "action_id": action_id,
            "action_db_id": str(action.id),
            "strategy": strategy,
            "parameters": body.parameters,
        },
        created_at=now,
    )
    db.add(audit_entry)
    await db.commit()

    job = "run_gitops_remediation" if strategy == GITOPS_PR else "run_remediation"
    await _enqueue_job(job, str(action.id))

    return {"action_id": str(action.id), "status": "PENDING", "strategy": strategy}


@router.post("/{incident_id}/actions/{action_db_id}/merged")
async def notify_pr_merged(
    incident_id: str,
    action_db_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Called after a GitOps PR is merged (by operator or GitHub webhook).
    Applies the patch to the cluster and enqueues the 5-minute verification job.
    """
    import subprocess

    try:
        inc_uuid = uuid.UUID(incident_id)
        action_uuid = uuid.UUID(action_db_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    result = await db.execute(
        select(RemediationAction).where(RemediationAction.id == action_uuid)
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    if action.remediation_strategy != GITOPS_PR:
        raise HTTPException(
            status_code=400, detail="This action is not a GITOPS_PR action"
        )

    if action.status != ActionStatus.PENDING_MERGE:
        raise HTTPException(
            status_code=409,
            detail=f"Action is in status {action.status.value}, expected PENDING_MERGE",
        )

    now = datetime.now(timezone.utc)
    action.status = ActionStatus.RUNNING
    action.started_at = now

    audit = AuditLog(
        id=uuid.uuid4(),
        incident_id=inc_uuid,
        actor_type="user",
        actor_id="operator",
        event_type="gitops.pr_merged",
        message=f"PR #{action.pr_number} merged — applying patch and starting verification",
        extra_metadata={"pr_number": action.pr_number, "pr_url": action.pr_url},
        created_at=now,
    )
    db.add(audit)
    await db.commit()

    # Apply the patch to the k8s cluster if we have the content
    if action.patch_content:
        try:
            proc = subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input=action.patch_content,
                capture_output=True,
                text=True,
                timeout=30,
            )
            log.info(
                "kubectl apply completed",
                returncode=proc.returncode,
                stdout=proc.stdout[:200],
            )
        except Exception as exc:
            log.error("kubectl apply failed", error=str(exc))

    # Enqueue 5-minute verification
    await _enqueue_job("verify_remediation", incident_id, action_db_id)

    return {"status": "verification_started", "action_id": action_db_id}


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
            "remediation_strategy": a.remediation_strategy,
            "pr_url": a.pr_url,
            "pr_number": a.pr_number,
            "pr_branch": a.pr_branch,
            "patch_file_path": a.patch_file_path,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in actions
    ]
