"""
github_correlation/correlator.py
----------------------------------
Pure correlation logic + main entry point ``correlate_incident()``.

``compute_correlation()`` is a pure function (no I/O) so it is easy
to unit-test independently of the HTTP adapter.

``correlate_incident()`` orchestrates adapter calls and passes results
to ``compute_correlation()``.  It never raises — on any failure it
returns ``ChangeContext(available=False)``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from github_correlation.adapter import GitHubCorrelationAdapter
from github_correlation.config import GitHubCorrelationConfig
from github_correlation.models import (
    ChangeContext,
    ChangedFileSummary,
    CommitSummary,
    DeployEvent,
    PullRequestSummary,
)

log = logging.getLogger(__name__)

# Max changed files to store in the evidence record (keeps the JSONB small)
_MAX_FILES_SAMPLE = 50


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _dedup_commits(commits: list[CommitSummary]) -> list[CommitSummary]:
    seen: set[str] = set()
    result = []
    for c in commits:
        if c.sha not in seen:
            seen.add(c.sha)
            result.append(c)
    return result


def _dedup_prs(prs: list[PullRequestSummary]) -> list[PullRequestSummary]:
    seen: set[int] = set()
    result = []
    for p in prs:
        if p.number not in seen:
            seen.add(p.number)
            result.append(p)
    return result


def _dedup_deploys(deploys: list[DeployEvent]) -> list[DeployEvent]:
    seen: set[str] = set()
    result = []
    for d in deploys:
        if d.id not in seen:
            seen.add(d.id)
            result.append(d)
    return result


# --------------------------------------------------------------------------- #
# Pure correlation logic
# --------------------------------------------------------------------------- #


def compute_correlation(
    *,
    repo: str,
    service: str,
    environment: str,
    incident_timestamp: datetime,
    window_minutes: int,
    regression_threshold_minutes: int,
    commits: list[CommitSummary],
    prs: list[PullRequestSummary],
    deploys: list[DeployEvent],
    changed_files: list[ChangedFileSummary],
) -> ChangeContext:
    """
    Pure function: take pre-fetched data and produce a ChangeContext.

    Sorting conventions:
      - commits:  newest-first (by timestamp)
      - prs:      newest merged-first
      - deploys:  newest-first (by timestamp)

    Regression detection:
      The ``closest_deploy`` is the most recent DeployEvent whose
      timestamp is strictly before ``incident_timestamp``.
      If it falls within ``regression_threshold_minutes`` of the
      incident, ``likely_regression = True``.
    """
    inc_ts = _utc(incident_timestamp)
    window_start = inc_ts - timedelta(minutes=window_minutes)

    # --- De-duplicate ---
    commits = _dedup_commits(commits)
    prs = _dedup_prs(prs)
    deploys = _dedup_deploys(deploys)

    # --- Filter to window [window_start, inc_ts] ---
    commits = [c for c in commits if window_start <= _utc(c.timestamp) <= inc_ts]
    prs = [
        p for p in prs
        if p.merged_at is not None and window_start <= _utc(p.merged_at) <= inc_ts
    ]
    deploys = [
        d for d in deploys
        if window_start <= _utc(d.timestamp) <= inc_ts
    ]

    # --- Sort newest-first ---
    commits.sort(key=lambda c: _utc(c.timestamp), reverse=True)
    prs.sort(key=lambda p: _utc(p.merged_at), reverse=True)   # type: ignore[arg-type]
    deploys.sort(key=lambda d: _utc(d.timestamp), reverse=True)

    # --- Regression detection ---
    closest_deploy: Optional[DeployEvent] = deploys[0] if deploys else None
    likely_regression = False
    regression_window_minutes: Optional[int] = None

    if closest_deploy is not None:
        delta = inc_ts - _utc(closest_deploy.timestamp)
        minutes_since = int(delta.total_seconds() / 60)
        regression_window_minutes = minutes_since
        if minutes_since <= regression_threshold_minutes:
            likely_regression = True

    return ChangeContext(
        available=True,
        repo=repo,
        service=service,
        environment=environment,
        incident_timestamp=inc_ts,
        window_start=window_start,
        window_end=inc_ts,
        recent_commits=commits,
        recent_prs=prs,
        recent_deploys=deploys,
        likely_regression=likely_regression,
        regression_window_minutes=regression_window_minutes,
        closest_deploy=closest_deploy,
        changed_files_sample=changed_files[:_MAX_FILES_SAMPLE],
        total_commits=len(commits),
        total_prs_merged=len(prs),
    )


# --------------------------------------------------------------------------- #
# Main entry point (I/O)
# --------------------------------------------------------------------------- #


async def correlate_incident(
    *,
    incident_timestamp: datetime,
    service: str,
    environment: str,
    config: Optional[GitHubCorrelationConfig] = None,
) -> ChangeContext:
    """
    Fetch GitHub data and return a ChangeContext for the given incident.

    Always returns a valid ChangeContext — never raises.  When GitHub is
    unavailable or unconfigured, returns ``ChangeContext(available=False)``.
    """
    if config is None:
        config = GitHubCorrelationConfig()

    repo = config.repo_for_service(service)
    if not repo:
        log.info(
            "github_correlation.skipped: no repo configured for service=%s", service
        )
        return ChangeContext(
            available=False,
            error_message=f"No GitHub repo configured for service '{service}'",
            service=service,
            environment=environment,
        )

    inc_ts = _utc(incident_timestamp)
    window_start = inc_ts - timedelta(minutes=config.github_correlation_window_minutes)

    adapter = GitHubCorrelationAdapter(config)
    try:
        # Fetch all sources in parallel; individual failures return []
        commits, prs, releases = await asyncio.gather(
            adapter.get_commits(repo, since=window_start, until=inc_ts),
            adapter.get_merged_prs_any_base(repo, since=window_start, until=inc_ts),
            adapter.get_recent_releases(repo, since=window_start, until=inc_ts),
        )

        # Build deploy events: prefer releases; fall back to PR merges
        deploys: list[DeployEvent] = releases or adapter.deploy_events_from_prs(prs)

        # Fetch changed files between oldest and newest commits in window
        changed_files: list[ChangedFileSummary] = []
        if len(commits) >= 2:
            oldest_sha = commits[-1].sha
            newest_sha = commits[0].sha
            changed_files = await adapter.get_changed_files(
                repo, base_sha=oldest_sha, head_sha=newest_sha
            )

        return compute_correlation(
            repo=repo,
            service=service,
            environment=environment,
            incident_timestamp=inc_ts,
            window_minutes=config.github_correlation_window_minutes,
            regression_threshold_minutes=config.github_regression_threshold_minutes,
            commits=commits,
            prs=prs,
            deploys=deploys,
            changed_files=changed_files,
        )

    except Exception as exc:
        log.warning(
            "github_correlation.error service=%s repo=%s: %s", service, repo, exc
        )
        return ChangeContext(
            available=False,
            error_message=str(exc),
            repo=repo,
            service=service,
            environment=environment,
        )
    finally:
        await adapter.close()
