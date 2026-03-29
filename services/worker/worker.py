"""
SelfOps ARQ worker.

Job functions:
  - enrich_incident   : fetch Prometheus metrics + Loki logs, store as evidence
  - analyze_incident  : call analysis service, store result, update status
  - notify_incident   : send Telegram notification
  - run_remediation   : run Ansible playbook, update action status, notify
"""

import asyncio
import json
import subprocess
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import structlog
from arq.connections import RedisSettings
from pydantic_settings import BaseSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class WorkerConfig(BaseSettings):
    database_url: str = (
        "postgresql+asyncpg://selfops:password"
        "@postgres-postgresql.platform.svc.cluster.local:5432/selfops"
    )
    redis_url: str = "redis://redis-master.platform.svc.cluster.local:6379"
    prometheus_url: str = (
        "http://prometheus-operated.monitoring.svc.cluster.local:9090"
    )
    loki_url: str = "http://loki.monitoring.svc.cluster.local:3100"
    analysis_service_url: str = (
        "http://selfops-analysis.platform.svc.cluster.local:8001"
    )
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    frontend_url: str = "http://localhost:3000"

    class Config:
        env_file = ".env"


config = WorkerConfig()

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

_engine = None
_session_factory = None


def _get_session_factory():
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_async_engine(config.database_url, echo=False)
        _session_factory = async_sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


# ---------------------------------------------------------------------------
# Inline model definitions (mirrors services/api/app/models.py)
# ---------------------------------------------------------------------------

import enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class IncidentStatus(str, enum.Enum):
    OPEN = "OPEN"
    ENRICHING = "ENRICHING"
    ANALYZING = "ANALYZING"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    REMEDIATING = "REMEDIATING"
    MONITORING = "MONITORING"
    RESOLVED = "RESOLVED"
    FAILED_REMEDIATION = "FAILED_REMEDIATION"
    CLOSED = "CLOSED"


class SeverityLevel(str, enum.Enum):
    critical = "critical"
    warning = "warning"
    info = "info"
    unknown = "unknown"


class ActionStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING_MERGE = "PENDING_MERGE"


class ExecutionMode(str, enum.Enum):
    manual = "manual"
    auto = "auto"


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[IncidentStatus] = mapped_column(
        SAEnum(IncidentStatus, name="incident_status")
    )
    severity: Mapped[SeverityLevel] = mapped_column(
        SAEnum(SeverityLevel, name="severity_level")
    )
    service_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    namespace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    environment: Mapped[Optional[str]] = mapped_column(Text)
    fingerprint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True
    )
    alert_name: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(Text)
    labels: Mapped[Optional[dict]] = mapped_column(JSON)
    annotations: Mapped[Optional[dict]] = mapped_column(JSON)
    starts_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class IncidentEvidence(Base):
    __tablename__ = "incident_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True
    )
    evidence_type: Mapped[str] = mapped_column(String(50))
    content: Mapped[dict] = mapped_column(JSON)
    captured_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True
    )
    model_provider: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    probable_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_action_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    escalate: Mapped[Optional[bool]] = mapped_column(Boolean)
    raw_output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    investigation_log: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    structured_analysis: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RemediationAction(Base):
    __tablename__ = "remediation_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(Text)
    action_name: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(Text)
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        SAEnum(ExecutionMode, name="execution_mode")
    )
    status: Mapped[ActionStatus] = mapped_column(
        SAEnum(ActionStatus, name="action_status")
    )
    parameters: Mapped[Optional[dict]] = mapped_column(JSON)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # GitOps fields
    remediation_strategy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pr_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pr_number: Mapped[Optional[int]] = mapped_column(nullable=True)
    pr_branch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    patch_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    patch_file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(50))
    actor_id: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    extra_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSON)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ---------------------------------------------------------------------------
# Allowed actions (mirrors services/api/app/routers/actions.py)
# ---------------------------------------------------------------------------

ALLOWED_ACTIONS: dict[str, dict] = {
    "restart_deployment": {
        "name": "Restart Deployment",
        "playbook": "remediation/restart_deployment.yml",
        "safe_for_auto": False,
        "required_params": ["deployment_name", "namespace"],
        "allowed_namespaces": ["platform"],
    },
    "rollout_restart": {
        "name": "Rollout Restart",
        "playbook": "remediation/rollout_restart.yml",
        "safe_for_auto": False,
        "required_params": ["deployment_name", "namespace"],
        "allowed_namespaces": ["platform"],
    },
    "scale_up": {
        "name": "Scale Up Replicas",
        "playbook": "remediation/scale_up.yml",
        "safe_for_auto": False,
        "required_params": ["deployment_name", "namespace", "max_replicas"],
        "allowed_namespaces": ["platform"],
    },
}


# ---------------------------------------------------------------------------
# Job: enrich_incident
# ---------------------------------------------------------------------------


async def enrich_incident(ctx: dict, incident_id: str) -> None:
    """Fetch Prometheus metrics and Loki logs, store as incident_evidence."""
    log.info("enrich_incident started", incident_id=incident_id)
    session_factory = _get_session_factory()
    now = datetime.now(timezone.utc)

    async with session_factory() as db:
        result = await db.execute(
            select(Incident).where(Incident.id == uuid.UUID(incident_id))
        )
        incident = result.scalar_one_or_none()
        if not incident:
            log.error("Incident not found", incident_id=incident_id)
            return

        # Update status to ENRICHING
        incident.status = IncidentStatus.ENRICHING
        incident.updated_at = now
        await db.commit()

        namespace = incident.namespace or "platform"

        async with httpx.AsyncClient(timeout=30.0) as client:
            # --- Prometheus metrics ---
            try:
                prom_query = (
                    f'kube_pod_container_status_restarts_total{{namespace="{namespace}"}}'
                )
                prom_resp = await client.get(
                    f"{config.prometheus_url}/api/v1/query",
                    params={"query": prom_query},
                )
                metrics_content = prom_resp.json()
            except Exception as exc:
                log.warning("Prometheus query failed", error=str(exc))
                metrics_content = {"error": str(exc)}

            evidence_metric = IncidentEvidence(
                id=uuid.uuid4(),
                incident_id=incident.id,
                evidence_type="metric",
                content=metrics_content,
                captured_at=now,
            )
            db.add(evidence_metric)

            # --- Loki logs ---
            try:
                five_min_ago_ns = int(
                    (now - timedelta(minutes=5)).timestamp() * 1_000_000_000
                )
                now_ns = int(now.timestamp() * 1_000_000_000)
                loki_resp = await client.get(
                    f"{config.loki_url}/loki/api/v1/query_range",
                    params={
                        "query": f'{{namespace="{namespace}"}}',
                        "limit": 50,
                        "start": five_min_ago_ns,
                        "end": now_ns,
                    },
                )
                logs_content = loki_resp.json()
            except Exception as exc:
                log.warning("Loki query failed", error=str(exc))
                logs_content = {"error": str(exc)}

            evidence_log = IncidentEvidence(
                id=uuid.uuid4(),
                incident_id=incident.id,
                evidence_type="log",
                content=logs_content,
                captured_at=now,
            )
            db.add(evidence_log)

        # --- GitHub deploy correlation (optional, non-fatal) ---
        try:
            from github_correlation import correlate_incident as _correlate
            from github_correlation.config import GitHubCorrelationConfig

            gh_config = GitHubCorrelationConfig()
            inc_ts = incident.created_at or now
            change_ctx = await _correlate(
                incident_timestamp=inc_ts,
                service=incident.service_name or "",
                environment=incident.environment or "production",
                config=gh_config,
            )
            if change_ctx.available:
                evidence_deploy = IncidentEvidence(
                    id=uuid.uuid4(),
                    incident_id=incident.id,
                    evidence_type="deploy_correlation",
                    content=change_ctx.model_dump(mode="json"),
                    captured_at=now,
                )
                db.add(evidence_deploy)
                await db.commit()
                log.info(
                    "github_correlation stored",
                    incident_id=incident_id,
                    repo=change_ctx.repo,
                    commits=change_ctx.total_commits,
                    deploys=len(change_ctx.recent_deploys),
                    likely_regression=change_ctx.likely_regression,
                )
        except Exception as _gh_exc:
            log.warning(
                "github_correlation failed (non-fatal)",
                incident_id=incident_id,
                error=str(_gh_exc),
            )

        # --- PostgreSQL diagnostics (optional, non-fatal) ---
        try:
            from pg_diagnostics import fetch_diagnostics as _fetch_pg
            from pg_diagnostics.config import PgDiagnosticsConfig

            pg_config = PgDiagnosticsConfig()
            if pg_config.pg_diagnostics_enabled:
                db_diag = await _fetch_pg(config=pg_config)
                evidence_db = IncidentEvidence(
                    id=uuid.uuid4(),
                    incident_id=incident.id,
                    evidence_type="database",
                    content=db_diag.model_dump(mode="json"),
                    captured_at=now,
                )
                db.add(evidence_db)
                await db.commit()
                log.info(
                    "pg_diagnostics stored",
                    incident_id=incident_id,
                    available=db_diag.available,
                    total_connections=db_diag.total_connections,
                    blocked=len(db_diag.blocked_queries),
                    long_idle=len(db_diag.long_idle_connections),
                )
        except Exception as _pg_exc:
            log.warning(
                "pg_diagnostics failed (non-fatal)",
                incident_id=incident_id,
                error=str(_pg_exc),
            )

        # Update status to ANALYZING
        incident.status = IncidentStatus.ANALYZING
        incident.updated_at = datetime.now(timezone.utc)
        await db.commit()

    log.info("enrich_incident complete", incident_id=incident_id)

    # Enqueue analysis
    from arq.connections import create_pool

    try:
        redis_settings = RedisSettings.from_dsn(config.redis_url)
        arq_redis = await create_pool(redis_settings)
        await arq_redis.enqueue_job("analyze_incident", incident_id)
        await arq_redis.aclose()
    except Exception as exc:
        log.error("Failed to enqueue analyze_incident", error=str(exc))


# ---------------------------------------------------------------------------
# Job: analyze_incident
# ---------------------------------------------------------------------------


def _format_metrics(content: dict) -> str:
    """Convert Prometheus query result to a human-readable text summary."""
    try:
        data = content.get("data", {})
        result = data.get("result", [])
        if not result:
            return "No metric data available"
        lines = []
        for item in result[:10]:
            metric = item.get("metric", {})
            value = item.get("value", [None, "N/A"])
            pod = metric.get("pod", metric.get("container", str(metric)))
            lines.append(f"  {pod}: {value[1]}")
        return "\n".join(lines)
    except Exception:
        return str(content)[:500]


def _format_logs(content: dict) -> str:
    """Extract last 20 log lines from a Loki query_range response."""
    try:
        data = content.get("data", {})
        streams = data.get("result", [])
        all_lines = []
        for stream in streams:
            values = stream.get("values", [])
            for ts, line in values:
                all_lines.append((ts, line))
        # Sort by timestamp (nanosecond string — lexicographic sort is fine here)
        all_lines.sort(key=lambda x: x[0])
        last_20 = all_lines[-20:]
        if not last_20:
            return "No log lines available"
        return "\n".join(line for _, line in last_20)
    except Exception:
        return str(content)[:500]


async def analyze_incident(ctx: dict, incident_id: str) -> None:
    """Call the analysis service and store the result."""
    log.info("analyze_incident started", incident_id=incident_id)
    session_factory = _get_session_factory()
    now = datetime.now(timezone.utc)

    async with session_factory() as db:
        result = await db.execute(
            select(Incident).where(Incident.id == uuid.UUID(incident_id))
        )
        incident = result.scalar_one_or_none()
        if not incident:
            log.error("Incident not found", incident_id=incident_id)
            return

        # Load evidence
        ev_result = await db.execute(
            select(IncidentEvidence).where(
                IncidentEvidence.incident_id == incident.id
            )
        )
        evidence_rows = ev_result.scalars().all()

        # Load first alert event
        ae_result = await db.execute(
            select(AlertEvent)
            .where(AlertEvent.incident_id == incident.id)
            .order_by(AlertEvent.created_at.asc())
            .limit(1)
        )
        first_alert = ae_result.scalar_one_or_none()

        metrics_text = "No metrics available"
        logs_text = "No logs available"
        for ev in evidence_rows:
            if ev.evidence_type == "metric":
                metrics_text = _format_metrics(ev.content)
            elif ev.evidence_type == "log":
                logs_text = _format_logs(ev.content)

        alert_name = first_alert.alert_name if first_alert else "Unknown"
        alert_labels = first_alert.labels if first_alert else {}
        alert_annotations = first_alert.annotations if first_alert else {}

        allowed_actions = [
            {
                "action_id": k,
                "name": v["name"],
                "description": v.get("description", ""),
            }
            for k, v in ALLOWED_ACTIONS.items()
        ]

        request_payload = {
            "incident_id": incident_id,
            "incident_title": incident.title,
            "service_name": incident.service_name or "",
            "namespace": incident.namespace or "",
            "alert_name": alert_name,
            "alert_labels": alert_labels or {},
            "alert_annotations": alert_annotations or {},
            "metrics_summary": metrics_text,
            "log_lines": logs_text,
            "allowed_actions": allowed_actions,
        }

        analysis_response = None
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                resp = await client.post(
                    f"{config.analysis_service_url}/analyze",
                    json=request_payload,
                )
                resp.raise_for_status()
                analysis_response = resp.json()
            except Exception as exc:
                log.error("Analysis service call failed", error=str(exc))
                analysis_response = {
                    "summary": "Analysis failed - analysis service unavailable",
                    "probable_cause": "Unknown - manual investigation required",
                    "evidence_points": [],
                    "recommended_action_id": None,
                    "confidence": 0.0,
                    "escalate": True,
                    "raw_output": {"error": str(exc)},
                }

        structured = analysis_response.get("structured")
        # Derive recommendation text from structured action_plan when available
        recommendation = analysis_response.get("recommendation", "")
        if not recommendation and structured and isinstance(structured, dict):
            plan = structured.get("action_plan", [])
            if plan and isinstance(plan, list) and plan[0]:
                recommendation = plan[0].get("description", "")

        analysis_row = AnalysisResult(
            id=uuid.uuid4(),
            incident_id=incident.id,
            model_provider="openrouter",
            model_name="anthropic/claude-3-haiku",
            prompt_version="v3-structured" if structured else "v2-react",
            summary=analysis_response.get("summary", ""),
            probable_cause=analysis_response.get("probable_cause", ""),
            recommendation=recommendation,
            recommended_action_id=analysis_response.get("recommended_action_id"),
            confidence_score=analysis_response.get("confidence", 0.0),
            escalate=analysis_response.get("escalate", False),
            raw_output=analysis_response.get("raw_output", analysis_response),
            investigation_log=analysis_response.get("investigation_log"),
            structured_analysis=structured,
            created_at=now,
        )
        db.add(analysis_row)

        incident.status = IncidentStatus.ACTION_REQUIRED
        incident.updated_at = datetime.now(timezone.utc)
        await db.commit()

    log.info("analyze_incident complete", incident_id=incident_id)

    # Enqueue notification
    from arq.connections import create_pool

    try:
        redis_settings = RedisSettings.from_dsn(config.redis_url)
        arq_redis = await create_pool(redis_settings)
        summary = analysis_response.get("summary", "")
        await arq_redis.enqueue_job(
            "notify_incident",
            incident_id,
            f"Analysis complete: {summary[:100]}",
        )
        await arq_redis.aclose()
    except Exception as exc:
        log.error("Failed to enqueue notify_incident", error=str(exc))


# ---------------------------------------------------------------------------
# Job: notify_incident
# ---------------------------------------------------------------------------


async def notify_incident(
    ctx: dict, incident_id: str, message: str = ""
) -> None:
    """Send a Telegram notification for the incident."""
    log.info("notify_incident started", incident_id=incident_id)

    if not config.telegram_bot_token or not config.telegram_chat_id:
        log.warning("Telegram credentials not configured, skipping notification")
        return

    session_factory = _get_session_factory()

    async with session_factory() as db:
        result = await db.execute(
            select(Incident).where(Incident.id == uuid.UUID(incident_id))
        )
        incident = result.scalar_one_or_none()
        if not incident:
            log.error("Incident not found for notification", incident_id=incident_id)
            return

        # Load latest analysis result
        ar_result = await db.execute(
            select(AnalysisResult)
            .where(AnalysisResult.incident_id == incident.id)
            .order_by(AnalysisResult.created_at.desc())
            .limit(1)
        )
        analysis = ar_result.scalar_one_or_none()

    severity = incident.severity.value if incident.severity else "unknown"
    status = incident.status.value if incident.status else "unknown"

    summary = analysis.summary if analysis else "No analysis available"
    probable_cause = analysis.probable_cause if analysis else "Unknown"
    recommendation = analysis.recommendation if analysis else "No recommendation"

    # Build plain-text message (avoids Markdown parse errors)
    text = (
        f"\U0001f6a8 SelfOps Alert\n"
        f"Incident: {incident.title}\n"
        f"Service: {incident.service_name or 'N/A'} | Namespace: {incident.namespace or 'N/A'}\n"
        f"Status: {status} | Severity: {severity}\n\n"
        f"Analysis: {summary}\n"
        f"Probable cause: {probable_cause}\n"
        f"Recommended action: {recommendation}\n\n"
        f"Dashboard: {config.frontend_url}/incidents/{incident_id}"
    )

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": config.telegram_chat_id,
                    "text": text,
                },
            )
            if not resp.is_success:
                log.error(
                    "Telegram notification failed",
                    status=resp.status_code,
                    body=resp.text[:500],
                )
            else:
                log.info("Telegram notification sent", incident_id=incident_id)
        except Exception as exc:
            log.error("Telegram notification failed", error=str(exc))


# ---------------------------------------------------------------------------
# Job: run_remediation
# ---------------------------------------------------------------------------


async def run_remediation(ctx: dict, action_db_id: str) -> None:
    """Execute an Ansible playbook for a remediation action."""
    log.info("run_remediation started", action_db_id=action_db_id)
    session_factory = _get_session_factory()
    now = datetime.now(timezone.utc)

    async with session_factory() as db:
        result = await db.execute(
            select(RemediationAction).where(
                RemediationAction.id == uuid.UUID(action_db_id)
            )
        )
        action = result.scalar_one_or_none()
        if not action:
            log.error("RemediationAction not found", action_db_id=action_db_id)
            return

        incident_id = str(action.incident_id)
        action_id = action.action_type
        parameters = action.parameters or {}

        # Validate action
        if action_id not in ALLOWED_ACTIONS:
            action.status = ActionStatus.FAILED
            action.completed_at = now
            action.result_summary = f"Action '{action_id}' not in allowed list"
            await db.commit()
            return

        action_def = ALLOWED_ACTIONS[action_id]
        for param in action_def["required_params"]:
            if param not in parameters:
                action.status = ActionStatus.FAILED
                action.completed_at = now
                action.result_summary = f"Missing required parameter: {param}"
                await db.commit()
                return

        namespace = parameters.get("namespace", "")
        if namespace and namespace not in action_def["allowed_namespaces"]:
            action.status = ActionStatus.FAILED
            action.completed_at = now
            action.result_summary = (
                f"Namespace '{namespace}' is not allowed for this action"
            )
            await db.commit()
            return

        # Mark as RUNNING
        action.status = ActionStatus.RUNNING
        action.started_at = now
        await db.commit()

    # Build extra-vars string
    extra_vars = json.dumps(parameters)
    playbook_path = f"/app/{action_def['playbook']}"

    try:
        proc = subprocess.run(
            ["ansible-playbook", playbook_path, "-e", extra_vars],
            capture_output=True,
            text=True,
            timeout=180,
        )
        success = proc.returncode == 0
        stdout = proc.stdout[:4000] if proc.stdout else ""
        stderr = proc.stderr[:2000] if proc.stderr else ""
        result_summary = (
            f"Exit code: {proc.returncode}\n{stdout}"
            if success
            else f"FAILED (exit {proc.returncode})\n{stderr}"
        )
        raw_output = {"stdout": stdout, "stderr": stderr, "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        success = False
        result_summary = "Ansible playbook timed out after 180 seconds"
        raw_output = {"error": "timeout"}
    except Exception as exc:
        success = False
        result_summary = f"Failed to run playbook: {exc}"
        raw_output = {"error": str(exc)}

    finished_at = datetime.now(timezone.utc)

    async with session_factory() as db:
        result = await db.execute(
            select(RemediationAction).where(
                RemediationAction.id == uuid.UUID(action_db_id)
            )
        )
        action = result.scalar_one_or_none()
        if action:
            action.status = ActionStatus.SUCCESS if success else ActionStatus.FAILED
            action.completed_at = finished_at
            action.result_summary = result_summary
            action.raw_output = raw_output

        # Write audit log
        audit_entry = AuditLog(
            id=uuid.uuid4(),
            incident_id=uuid.UUID(incident_id),
            actor_type="automation",
            actor_id="remediation-runner",
            event_type="action.completed" if success else "action.failed",
            message=(
                f"Remediation action {'succeeded' if success else 'failed'}: "
                f"{action.action_name if action else action_id}"
            ),
            extra_metadata=raw_output,
            created_at=finished_at,
        )
        db.add(audit_entry)
        await db.commit()

    log.info(
        "run_remediation complete",
        action_db_id=action_db_id,
        success=success,
    )

    # Send Telegram notification about the completed remediation
    from arq.connections import create_pool

    try:
        redis_settings = RedisSettings.from_dsn(config.redis_url)
        arq_redis = await create_pool(redis_settings)
        status_word = "succeeded" if success else "FAILED"
        await arq_redis.enqueue_job(
            "notify_incident",
            incident_id,
            f"Remediation action {status_word}: {action_id}",
        )
        await arq_redis.aclose()
    except Exception as exc:
        log.error("Failed to enqueue notify_incident after remediation", error=str(exc))


# ---------------------------------------------------------------------------
# Job: run_gitops_remediation
# ---------------------------------------------------------------------------


async def run_gitops_remediation(ctx: dict, action_db_id: str) -> None:
    """Create a GitHub branch, commit an AI-generated patch, open a PR."""
    log.info("run_gitops_remediation started", action_db_id=action_db_id)
    from jobs.github_client import create_branch, get_file, commit_file, create_pull_request
    from jobs.patch_generator import generate_patch, resolve_manifest_path

    session_factory = _get_session_factory()
    now = datetime.now(timezone.utc)

    async with session_factory() as db:
        result = await db.execute(
            select(RemediationAction).where(
                RemediationAction.id == uuid.UUID(action_db_id)
            )
        )
        action = result.scalar_one_or_none()
        if not action:
            log.error("RemediationAction not found", action_db_id=action_db_id)
            return

        incident_id = str(action.incident_id)

        result = await db.execute(
            select(Incident).where(Incident.id == action.incident_id)
        )
        incident = result.scalar_one_or_none()
        if not incident:
            log.error("Incident not found", incident_id=incident_id)
            return

        # Load latest analysis for context
        ar_result = await db.execute(
            select(AnalysisResult)
            .where(AnalysisResult.incident_id == action.incident_id)
            .order_by(AnalysisResult.created_at.desc())
            .limit(1)
        )
        analysis = ar_result.scalar_one_or_none()

        # Load first alert event for alert name
        ae_result = await db.execute(
            select(AlertEvent)
            .where(AlertEvent.incident_id == action.incident_id)
            .order_by(AlertEvent.created_at.asc())
            .limit(1)
        )
        first_alert = ae_result.scalar_one_or_none()

    alert_name = first_alert.alert_name if first_alert else "UnknownAlert"
    summary = analysis.summary if analysis else ""
    probable_cause = analysis.probable_cause if analysis else ""
    service_name = incident.service_name or "unknown-service"

    manifest_path = resolve_manifest_path(service_name)
    branch_name = f"fix/incident-{incident_id[:8]}-{int(now.timestamp())}"

    try:
        # 1. Get current manifest from GitHub
        file_data = await get_file(manifest_path)
        current_content = file_data["content"]
        file_sha = file_data["sha"]

        # 2. Generate patch via LLM
        patch = await generate_patch(
            incident_title=incident.title,
            service_name=service_name,
            alert_name=alert_name,
            analysis_summary=summary,
            probable_cause=probable_cause,
            current_manifest=current_content,
        )

        # 3. Create branch and commit patch
        await create_branch(branch_name)
        await commit_file(
            branch=branch_name,
            path=manifest_path,
            new_content=patch["new_content"],
            message=patch["commit_message"],
            file_sha=file_sha,
        )

        # 4. Open PR
        pr = await create_pull_request(
            branch=branch_name,
            title=patch["pr_title"],
            body=patch["pr_body"],
        )

        log.info(
            "GitOps PR created",
            pr_number=pr["number"],
            pr_url=pr["html_url"],
            branch=branch_name,
        )

        # 5. Update action record
        async with session_factory() as db:
            result = await db.execute(
                select(RemediationAction).where(
                    RemediationAction.id == uuid.UUID(action_db_id)
                )
            )
            action = result.scalar_one_or_none()
            if action:
                action.status = ActionStatus.PENDING_MERGE
                action.pr_url = pr["html_url"]
                action.pr_number = pr["number"]
                action.pr_branch = branch_name
                action.patch_content = patch["new_content"]
                action.patch_file_path = manifest_path
                action.result_summary = (
                    f"PR #{pr['number']} opened: {pr['html_url']}"
                )

            audit_entry = AuditLog(
                id=uuid.uuid4(),
                incident_id=uuid.UUID(incident_id),
                actor_type="automation",
                actor_id="selfops-agent",
                event_type="gitops.pr_created",
                message=(
                    f"GitOps PR #{pr['number']} created: {patch['description']} "
                    f"— {pr['html_url']}"
                ),
                extra_metadata={
                    "pr_number": pr["number"],
                    "pr_url": pr["html_url"],
                    "branch": branch_name,
                    "file": manifest_path,
                },
                created_at=datetime.now(timezone.utc),
            )
            db.add(audit_entry)
            await db.commit()

        # 6. Telegram notification
        from arq.connections import create_pool
        redis_settings = RedisSettings.from_dsn(config.redis_url)
        arq_redis = await create_pool(redis_settings)
        await arq_redis.enqueue_job(
            "notify_incident",
            incident_id,
            f"GitOps PR #{pr['number']} created — review and merge to apply fix: {pr['html_url']}",
        )
        await arq_redis.aclose()

    except Exception as exc:
        log.error("run_gitops_remediation failed", error=str(exc))
        async with session_factory() as db:
            result = await db.execute(
                select(RemediationAction).where(
                    RemediationAction.id == uuid.UUID(action_db_id)
                )
            )
            action = result.scalar_one_or_none()
            if action:
                action.status = ActionStatus.FAILED
                action.completed_at = datetime.now(timezone.utc)
                action.result_summary = f"GitOps PR creation failed: {exc}"
            audit_entry = AuditLog(
                id=uuid.uuid4(),
                incident_id=uuid.UUID(incident_id),
                actor_type="automation",
                actor_id="selfops-agent",
                event_type="gitops.pr_failed",
                message=f"GitOps PR creation failed: {exc}",
                extra_metadata={"error": str(exc)},
                created_at=datetime.now(timezone.utc),
            )
            db.add(audit_entry)
            await db.commit()


# ---------------------------------------------------------------------------
# Job: verify_remediation
# ---------------------------------------------------------------------------


async def verify_remediation(
    ctx: dict, incident_id: str, action_db_id: str
) -> None:
    """
    After a GitOps PR is merged and the patch applied, monitor the service
    for 5 minutes using Prometheus. Marks incident RESOLVED on success or
    reverts to ACTION_REQUIRED on failure.
    """
    log.info("verify_remediation started", incident_id=incident_id)
    session_factory = _get_session_factory()

    async with session_factory() as db:
        result = await db.execute(
            select(Incident).where(Incident.id == uuid.UUID(incident_id))
        )
        incident = result.scalar_one_or_none()
        if not incident:
            log.error("Incident not found for verification", incident_id=incident_id)
            return

        incident.status = IncidentStatus.MONITORING
        incident.updated_at = datetime.now(timezone.utc)

        audit = AuditLog(
            id=uuid.uuid4(),
            incident_id=uuid.UUID(incident_id),
            actor_type="automation",
            actor_id="selfops-agent",
            event_type="verification.started",
            message="Verification started — monitoring service health for 5 minutes",
            extra_metadata={},
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit)
        await db.commit()

    namespace = incident.namespace or "platform"
    service_name = incident.service_name or ""

    # Allow k8s to begin the rollout
    await asyncio.sleep(30)

    checks_passed = 0
    checks_total = 10  # 10 × 30s = 5 minutes
    consecutive_clean = 0
    required_consecutive = 3

    async with httpx.AsyncClient(timeout=15.0) as client:
        for check_num in range(1, checks_total + 1):
            try:
                # Check 1: restart rate in the last 2 minutes
                restart_query = (
                    f'rate(kube_pod_container_status_restarts_total'
                    f'{{namespace="{namespace}"}}[2m])'
                )
                r1 = await client.get(
                    f"{config.prometheus_url}/api/v1/query",
                    params={"query": restart_query},
                )
                restarts = r1.json().get("data", {}).get("result", [])
                any_restarting = any(
                    float(item.get("value", [0, "0"])[1]) > 0
                    for item in restarts
                    if isinstance(item, dict)
                )

                # Check 2: ready replicas match desired
                ready_query = (
                    f'kube_deployment_status_ready_replicas'
                    f'{{namespace="{namespace}"}}'
                )
                desired_query = (
                    f'kube_deployment_spec_replicas'
                    f'{{namespace="{namespace}"}}'
                )
                r2 = await client.get(
                    f"{config.prometheus_url}/api/v1/query",
                    params={"query": ready_query},
                )
                r3 = await client.get(
                    f"{config.prometheus_url}/api/v1/query",
                    params={"query": desired_query},
                )

                ready = {
                    item["metric"].get("deployment"): float(item["value"][1])
                    for item in r2.json().get("data", {}).get("result", [])
                    if isinstance(item, dict) and item.get("metric")
                }
                desired = {
                    item["metric"].get("deployment"): float(item["value"][1])
                    for item in r3.json().get("data", {}).get("result", [])
                    if isinstance(item, dict) and item.get("metric")
                }
                replicas_healthy = all(
                    ready.get(dep, 0) >= desired.get(dep, 1)
                    for dep in desired
                )

                is_healthy = (not any_restarting) and replicas_healthy

            except Exception as exc:
                log.warning("verification check failed", check=check_num, error=str(exc))
                is_healthy = False

            if is_healthy:
                consecutive_clean += 1
                checks_passed += 1
                log.info(
                    "verification check passed",
                    check=check_num,
                    consecutive=consecutive_clean,
                )
            else:
                consecutive_clean = 0
                log.info("verification check failed", check=check_num)

            if consecutive_clean >= required_consecutive:
                log.info(
                    "verification succeeded early",
                    checks=check_num,
                    passed=checks_passed,
                )
                break

            if check_num < checks_total:
                await asyncio.sleep(30)

    success = consecutive_clean >= required_consecutive
    finished_at = datetime.now(timezone.utc)

    async with session_factory() as db:
        result = await db.execute(
            select(Incident).where(Incident.id == uuid.UUID(incident_id))
        )
        incident = result.scalar_one_or_none()
        if incident:
            incident.status = (
                IncidentStatus.RESOLVED if success else IncidentStatus.ACTION_REQUIRED
            )
            if success:
                incident.resolved_at = finished_at
            incident.updated_at = finished_at

        result = await db.execute(
            select(RemediationAction).where(
                RemediationAction.id == uuid.UUID(action_db_id)
            )
        )
        action = result.scalar_one_or_none()
        if action:
            action.status = ActionStatus.SUCCESS if success else ActionStatus.FAILED
            action.completed_at = finished_at
            action.result_summary = (
                f"Service healthy after GitOps fix — incident resolved "
                f"({checks_passed}/{checks_total} checks passed)"
                if success
                else f"Service still unhealthy after 5 minutes "
                f"({checks_passed}/{checks_total} checks passed)"
            )

        verdict = "resolved" if success else "still unhealthy — escalating"
        audit = AuditLog(
            id=uuid.uuid4(),
            incident_id=uuid.UUID(incident_id),
            actor_type="automation",
            actor_id="selfops-agent",
            event_type="verification.completed" if success else "verification.failed",
            message=f"Verification complete — service is {verdict}",
            extra_metadata={
                "checks_passed": checks_passed,
                "checks_total": checks_total,
                "success": success,
            },
            created_at=finished_at,
        )
        db.add(audit)
        await db.commit()

    log.info("verify_remediation complete", success=success, incident_id=incident_id)

    # Telegram notification
    from arq.connections import create_pool
    redis_settings = RedisSettings.from_dsn(config.redis_url)
    arq_redis = await create_pool(redis_settings)
    msg = (
        f"Incident RESOLVED after GitOps fix — service healthy for 5 minutes"
        if success
        else f"Verification FAILED — service still unhealthy after fix, manual review required"
    )
    await arq_redis.enqueue_job("notify_incident", incident_id, msg)
    await arq_redis.aclose()


# ---------------------------------------------------------------------------
# ARQ WorkerSettings
# ---------------------------------------------------------------------------


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(config.redis_url)
    functions = [
        enrich_incident,
        analyze_incident,
        notify_incident,
        run_remediation,
        run_gitops_remediation,
        verify_remediation,
    ]
    max_jobs = 10
    job_timeout = 600  # verification can take up to 5+ minutes
