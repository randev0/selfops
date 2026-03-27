import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AuditLog

log = structlog.get_logger()

router = APIRouter()


@router.get("/{incident_id}/audit")
async def get_audit_log(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        inc_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident ID format")

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.incident_id == inc_uuid)
        .order_by(AuditLog.created_at.asc())
    )
    logs = result.scalars().all()

    return [
        {
            "id": str(entry.id),
            "actor_type": entry.actor_type,
            "actor_id": entry.actor_id,
            "event_type": entry.event_type,
            "message": entry.message,
            "metadata": entry.extra_metadata,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        for entry in logs
    ]
