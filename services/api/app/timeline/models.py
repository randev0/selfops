"""
timeline/models.py
------------------
Typed domain model for a single normalised timeline event.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, field_serializer


TimelineSource = Literal["alert", "evidence", "analysis", "action", "audit"]


class TimelineEvent(BaseModel):
    id: str
    incident_id: str
    timestamp: datetime
    event_type: str
    source: TimelineSource
    title: str
    description: str
    severity: Optional[str] = None
    metadata: dict[str, Any] = {}

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime) -> str:
        return dt.isoformat()
