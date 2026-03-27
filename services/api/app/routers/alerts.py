import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import AlertEvent, AuditLog, Incident, IncidentStatus, SeverityLevel

log = structlog.get_logger()

router = APIRouter()


class AlertmanagerAlert(BaseModel):
    status: str = "firing"
    labels: dict[str, Any] = {}
    annotations: dict[str, Any] = {}
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None
    fingerprint: Optional[str] = None
    generatorURL: Optional[str] = None


class AlertmanagerWebhook(BaseModel):
    receiver: Optional[str] = None
    status: Optional[str] = None
    alerts: list[AlertmanagerAlert] = []
    groupLabels: dict[str, Any] = {}
    commonLabels: dict[str, Any] = {}
    commonAnnotations: dict[str, Any] = {}
    externalURL: Optional[str] = None
    version: Optional[str] = None
    groupKey: Optional[str] = None


def _compute_fingerprint(alert: AlertmanagerAlert) -> str:
    if alert.fingerprint:
        return alert.fingerprint
    return hashlib.md5(
        json.dumps(alert.labels, sort_keys=True).encode()
    ).hexdigest()


def _parse_severity(labels: dict) -> SeverityLevel:
    raw = labels.get("severity", "unknown").lower()
    try:
        return SeverityLevel(raw)
    except ValueError:
        return SeverityLevel.unknown


def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        # Handle both Z and +00:00 suffixes
        dt_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(dt_str)
    except (ValueError, AttributeError):
        return None


async def _enqueue_job(job_name: str, *args) -> None:
    """Enqueue an ARQ job, logging and swallowing any Redis errors."""
    try:
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        arq_redis = await create_pool(redis_settings)
        await arq_redis.enqueue_job(job_name, *args)
        await arq_redis.aclose()
    except Exception as exc:
        log.error("Failed to enqueue job", job=job_name, error=str(exc))


@router.post("/webhook")
async def alertmanager_webhook(
    payload: AlertmanagerWebhook,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    for alert in payload.alerts:
        fingerprint = _compute_fingerprint(alert)
        labels = alert.labels
        annotations = alert.annotations
        alert_name = labels.get("alertname", "Unknown")

        try:
            # Check for existing incident with this fingerprint
            result = await db.execute(
                select(Incident).where(Incident.fingerprint == fingerprint)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update last_seen_at on existing incident
                existing.last_seen_at = now
                incident = existing
                log.info(
                    "Alert matched existing incident",
                    incident_id=str(incident.id),
                    fingerprint=fingerprint,
                )
            else:
                # Create a new incident
                title = (
                    f"{alert_name} in {labels.get('namespace', 'unknown')}"
                )
                incident = Incident(
                    id=uuid.uuid4(),
                    title=title,
                    status=IncidentStatus.OPEN,
                    severity=_parse_severity(labels),
                    service_name=labels.get("service", labels.get("alertname", "")),
                    namespace=labels.get("namespace", ""),
                    environment="production",
                    fingerprint=fingerprint,
                    first_seen_at=now,
                    last_seen_at=now,
                    created_at=now,
                    updated_at=now,
                )
                db.add(incident)
                await db.flush()  # get the ID before creating related rows

                # Write an audit log entry for incident creation
                audit_entry = AuditLog(
                    id=uuid.uuid4(),
                    incident_id=incident.id,
                    actor_type="system",
                    actor_id="alertmanager",
                    event_type="incident.created",
                    message=f"Incident created from alert: {alert_name}",
                    metadata={"fingerprint": fingerprint, "labels": labels},
                    created_at=now,
                )
                db.add(audit_entry)
                log.info(
                    "Created new incident",
                    incident_id=str(incident.id),
                    title=title,
                    fingerprint=fingerprint,
                )

            # Add alert event regardless of whether incident is new or existing
            starts_at = _parse_datetime(alert.startsAt)
            ends_at = _parse_datetime(alert.endsAt)
            # Treat the epoch zero date (0001-01-01) as None
            if ends_at and ends_at.year < 2000:
                ends_at = None

            alert_event = AlertEvent(
                id=uuid.uuid4(),
                incident_id=incident.id,
                alert_name=alert_name,
                fingerprint=fingerprint,
                labels=labels,
                annotations=annotations,
                starts_at=starts_at,
                ends_at=ends_at,
                raw_payload=alert.model_dump(),
                created_at=now,
            )
            db.add(alert_event)
            await db.commit()

            # Enqueue enrichment only for newly created incidents
            if not existing:
                await _enqueue_job("enrich_incident", str(incident.id))

        except Exception as exc:
            await db.rollback()
            log.error(
                "Error processing alert",
                alert_name=alert_name,
                fingerprint=fingerprint,
                error=str(exc),
            )

    return {"status": "ok"}
