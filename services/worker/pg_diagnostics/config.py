"""
pg_diagnostics/config.py
-------------------------
Configuration for the PostgreSQL diagnostics adapter.

All settings are read from environment variables (or a .env file).

Minimal setup (uses the worker's own DATABASE_URL):
  # no config needed — adapter falls back to DATABASE_URL automatically

Explicit target (separate monitoring user, separate host):
  PG_DIAGNOSTICS_DSN=postgresql://selfops_monitor:pass@db-host:5432/selfops

Time and safety controls:
  PG_DIAGNOSTICS_QUERY_TIMEOUT_SECONDS=10
  PG_DIAGNOSTICS_MAX_ROWS=50
  PG_DIAGNOSTICS_LONG_IDLE_THRESHOLD_SECONDS=300
  PG_DIAGNOSTICS_MAX_QUERY_LENGTH=500
"""
from __future__ import annotations

import os
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class PgDiagnosticsConfig(BaseSettings):
    # ---- Target DSN ----
    # asyncpg-format DSN (postgresql://...).
    # If empty, falls back to DATABASE_URL with the '+asyncpg' driver prefix
    # stripped.  If neither is set, diagnostics are skipped.
    pg_diagnostics_dsn: str = ""

    # ---- Feature flag ----
    pg_diagnostics_enabled: bool = True

    # ---- Safety limits ----
    pg_diagnostics_query_timeout_seconds: float = 10.0
    pg_diagnostics_max_rows: int = 50
    pg_diagnostics_max_query_length: int = 500

    # ---- Thresholds ----
    # Connections idle longer than this (seconds) appear in long_idle_connections
    pg_diagnostics_long_idle_threshold_seconds: int = 300  # 5 minutes

    model_config = {"env_file": ".env", "extra": "ignore"}

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("pg_diagnostics_query_timeout_seconds", mode="before")
    @classmethod
    def _clamp_timeout(cls, v: float) -> float:
        return max(1.0, min(float(v), 60.0))

    @field_validator("pg_diagnostics_max_rows", mode="before")
    @classmethod
    def _clamp_rows(cls, v: int) -> int:
        return max(1, min(int(v), 500))

    @field_validator("pg_diagnostics_max_query_length", mode="before")
    @classmethod
    def _clamp_query_length(cls, v: int) -> int:
        return max(50, min(int(v), 2000))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def effective_dsn(self) -> Optional[str]:
        """
        Return the asyncpg-compatible DSN to connect to, or None if
        no DSN is configured.

        Priority:
          1. PG_DIAGNOSTICS_DSN (explicit)
          2. DATABASE_URL stripped of the '+asyncpg' SQLAlchemy prefix
        """
        if self.pg_diagnostics_dsn:
            return self.pg_diagnostics_dsn
        db_url = os.environ.get("DATABASE_URL", "")
        if db_url:
            return db_url.replace("postgresql+asyncpg://", "postgresql://")
        return None

    @property
    def statement_timeout_ms(self) -> int:
        return int(self.pg_diagnostics_query_timeout_seconds * 1000)
