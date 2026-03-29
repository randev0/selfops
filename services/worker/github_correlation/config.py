"""
github_correlation/config.py
-----------------------------
Configuration for the GitHub correlation adapter.

All settings are read from environment variables (or a .env file).
The ``github_`` prefix is baked into every field name so no separate
env-prefix is needed.

Minimal config (single repo for all services):
  GITHUB_TOKEN=ghp_...
  GITHUB_DEFAULT_REPO=owner/repo

Per-service mapping (JSON dict, service name → owner/repo):
  GITHUB_SERVICE_REPOS={"payment-worker":"org/payments","auth-service":"org/auth"}

Time-window control:
  GITHUB_CORRELATION_WINDOW_MINUTES=240     # look-back window (default 4 h)
  GITHUB_REGRESSION_THRESHOLD_MINUTES=60   # flag regression if deploy < N min before incident
"""
from __future__ import annotations

import json
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class GitHubCorrelationConfig(BaseSettings):
    # ---------- Auth ----------
    github_token: str = ""

    # ---------- Repo routing ----------
    # Fallback repo when no per-service mapping matches.
    # If empty *and* no mapping matches, correlation is skipped.
    github_default_repo: str = ""

    # JSON dict: {"service-name": "owner/repo", ...}
    # Loaded from env var GITHUB_SERVICE_REPOS
    github_service_repos_json: str = ""

    # ---------- Time windows ----------
    github_correlation_window_minutes: int = 240   # 4 hours
    github_regression_threshold_minutes: int = 60  # 1 hour

    # ---------- API limits ----------
    github_max_items_per_page: int = 30

    # ---------- Endpoint (override for GitHub Enterprise) ----------
    github_api_base_url: str = "https://api.github.com"

    model_config = {"env_file": ".env", "extra": "ignore"}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @field_validator("github_max_items_per_page", mode="before")
    @classmethod
    def _cap_per_page(cls, v: int) -> int:
        return max(1, min(int(v), 100))

    def _service_repo_map(self) -> dict[str, str]:
        """Parse the JSON service→repo mapping, tolerating bad JSON."""
        if not self.github_service_repos_json.strip():
            return {}
        try:
            raw = json.loads(self.github_service_repos_json)
            return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
        except (ValueError, TypeError):
            return {}

    def repo_for_service(self, service: str) -> Optional[str]:
        """
        Return the owner/repo string for a service, or None if unconfigured.

        Lookup order:
          1. Exact match in GITHUB_SERVICE_REPOS
          2. Prefix match (mapping key ends with "*")
          3. GITHUB_DEFAULT_REPO fallback
        """
        mapping = self._service_repo_map()

        # 1. Exact match
        if service in mapping:
            return mapping[service]

        # 2. Prefix match
        for pattern, repo in mapping.items():
            if pattern.endswith("*") and service.startswith(pattern[:-1]):
                return repo

        # 3. Default
        return self.github_default_repo or None
