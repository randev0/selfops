"""
github_correlation/models.py
-----------------------------
Typed domain models for GitHub deploy/change correlation.

These models are serialised to JSON and stored in
IncidentEvidence(evidence_type="deploy_correlation").
The timeline aggregator reads the JSON back and emits
TimelineEvent(source="deploy") objects.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CommitSummary(BaseModel):
    sha: str
    short_sha: str
    author: str
    author_email: Optional[str] = None
    message: str                          # first subject line, max 200 chars
    timestamp: datetime
    url: Optional[str] = None


class ChangedFileSummary(BaseModel):
    filename: str
    status: str                           # added | modified | removed | renamed
    additions: int = 0
    deletions: int = 0
    blob_url: Optional[str] = None


class PullRequestSummary(BaseModel):
    number: int
    title: str
    state: str                            # open | closed
    author: str
    merged_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    url: str
    merge_commit_sha: Optional[str] = None
    changed_files: int = 0
    labels: list[str] = Field(default_factory=list)
    head_ref: Optional[str] = None
    base_ref: Optional[str] = None


class DeployEvent(BaseModel):
    """
    A deploy / release marker in the repository.

    kind values:
      "release"       – a GitHub Release/tag was published
      "pr_merge"      – a PR was merged to the deployment branch
      "direct_commit" – a direct push to the default branch (no PR)
    """
    id: str                               # e.g. "release-42" or "pr-merge-17"
    kind: str
    ref: str                              # tag name, branch, or commit sha
    timestamp: datetime
    title: str
    url: Optional[str] = None
    commit_sha: Optional[str] = None
    author: Optional[str] = None
    # Extracted hints; may be None or wrong — treat as best-effort only
    image_tag_hint: Optional[str] = None
    config_version_hint: Optional[str] = None


class ChangeContext(BaseModel):
    """
    Aggregated result of GitHub deploy/change correlation for one incident.

    ``available = False`` indicates that GitHub data could not be fetched
    (missing token, repo not configured, API error).  Downstream consumers
    must check this flag before relying on the other fields.
    """
    available: bool
    error_message: Optional[str] = None

    repo: Optional[str] = None            # owner/repo
    service: Optional[str] = None
    environment: Optional[str] = None

    incident_timestamp: Optional[datetime] = None
    window_start: Optional[datetime] = None   # oldest boundary of look-back
    window_end: Optional[datetime] = None     # = incident_timestamp

    # Raw data from GitHub (sorted newest-first within each list)
    recent_commits: list[CommitSummary] = Field(default_factory=list)
    recent_prs: list[PullRequestSummary] = Field(default_factory=list)
    recent_deploys: list[DeployEvent] = Field(default_factory=list)

    # Correlation signals
    likely_regression: bool = False
    regression_window_minutes: Optional[int] = None  # minutes since closest deploy
    closest_deploy: Optional[DeployEvent] = None

    # Sample of files changed across the whole look-back window
    changed_files_sample: list[ChangedFileSummary] = Field(default_factory=list)
    total_commits: int = 0
    total_prs_merged: int = 0
