import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Text, DateTime, Float, Boolean, ForeignKey,
    Enum as SAEnum, JSON, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


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


class ExecutionMode(str, enum.Enum):
    manual = "manual"
    auto = "auto"


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        SAEnum(IncidentStatus, name="incident_status"),
        nullable=False,
        default=IncidentStatus.OPEN,
    )
    severity: Mapped[SeverityLevel] = mapped_column(
        SAEnum(SeverityLevel, name="severity_level"),
        nullable=False,
        default=SeverityLevel.unknown,
    )
    service_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    namespace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    environment: Mapped[Optional[str]] = mapped_column(Text, default="production")
    fingerprint: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )

    alert_events: Mapped[list["AlertEvent"]] = relationship(
        "AlertEvent", back_populates="incident", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["IncidentEvidence"]] = relationship(
        "IncidentEvidence", back_populates="incident", cascade="all, delete-orphan"
    )
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(
        "AnalysisResult", back_populates="incident", cascade="all, delete-orphan"
    )
    remediation_actions: Mapped[list["RemediationAction"]] = relationship(
        "RemediationAction", back_populates="incident", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="incident", cascade="all, delete-orphan"
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True
    )
    alert_name: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    labels: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    annotations: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    starts_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )

    incident: Mapped[Optional["Incident"]] = relationship(
        "Incident", back_populates="alert_events"
    )


class IncidentEvidence(Base):
    __tablename__ = "incident_evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True
    )
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )

    incident: Mapped[Optional["Incident"]] = relationship(
        "Incident", back_populates="evidence"
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True
    )
    model_provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False, default="v1")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    probable_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_action_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    escalate: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    raw_output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    investigation_log: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )

    incident: Mapped[Optional["Incident"]] = relationship(
        "Incident", back_populates="analysis_results"
    )


class RemediationAction(Base):
    __tablename__ = "remediation_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    action_name: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[str] = mapped_column(Text, nullable=False, default="operator")
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        SAEnum(ExecutionMode, name="execution_mode"),
        nullable=False,
        default=ExecutionMode.manual,
    )
    status: Mapped[ActionStatus] = mapped_column(
        SAEnum(ActionStatus, name="action_status"),
        nullable=False,
        default=ActionStatus.PENDING,
    )
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )

    incident: Mapped[Optional["Incident"]] = relationship(
        "Incident", back_populates="remediation_actions"
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[str] = mapped_column(Text, nullable=False, default="system")
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    extra_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )

    incident: Mapped[Optional["Incident"]] = relationship(
        "Incident", back_populates="audit_logs"
    )
