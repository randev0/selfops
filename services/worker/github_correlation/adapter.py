"""
github_correlation/adapter.py
------------------------------
Async GitHub REST API adapter for *reading* deploy/change data.

This is a read-only adapter (no writes).  All methods return empty lists
or None on error — they never propagate HTTP exceptions to callers.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from github_correlation.config import GitHubCorrelationConfig
from github_correlation.models import (
    ChangedFileSummary,
    CommitSummary,
    DeployEvent,
    PullRequestSummary,
)

log = logging.getLogger(__name__)

# Regex for extracting image tag / semver hints from release body text
_IMAGE_RE = re.compile(r'image[=:\s]+\S+:([\w.\-]+)', re.IGNORECASE)
_SEMVER_RE = re.compile(r'\bv?(\d+\.\d+\.\d+(?:[.\-]\w+)?)\b')


def _parse_dt(raw: str) -> datetime:
    """Parse ISO 8601 string → aware UTC datetime; returns epoch on failure."""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _parse_dt_opt(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return _parse_dt(str(raw))
    except Exception:
        return None


def _extract_image_hint(body: str, tag: str) -> Optional[str]:
    m = _IMAGE_RE.search(body)
    if m:
        return m.group(1)
    # Use the tag itself if it looks like a semver/version string
    m2 = _SEMVER_RE.match(tag)
    return tag if m2 else None


def _extract_version_hint(body: str, tag: str) -> Optional[str]:
    m = _SEMVER_RE.search(tag)
    return m.group(0) if m else None


class GitHubCorrelationAdapter:
    """
    Thin async wrapper around GitHub REST API v3 for correlation reads.

    Lifecycle: create once per enrichment task, ``await adapter.close()``
    when done.  A single httpx.AsyncClient is reused across all calls.
    """

    def __init__(self, config: GitHubCorrelationConfig) -> None:
        self._config = config
        self._base = config.github_api_base_url.rstrip("/")
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if config.github_token:
            headers["Authorization"] = f"Bearer {config.github_token}"
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=15.0,
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> Any:
        """Raw GET; raises httpx.HTTPError on non-2xx."""
        resp = await self._client.get(f"{self._base}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Commits
    # ------------------------------------------------------------------

    async def get_commits(
        self,
        repo: str,
        since: datetime,
        until: datetime,
        sha: str = "HEAD",
    ) -> list[CommitSummary]:
        """
        Return commits on *sha* (default: HEAD/default branch) in [since, until].
        Returns [] on any error.
        """
        try:
            data = await self._get(
                f"/repos/{repo}/commits",
                params={
                    "sha": sha,
                    "since": since.isoformat(),
                    "until": until.isoformat(),
                    "per_page": self._config.github_max_items_per_page,
                },
            )
            return [
                self._parse_commit(c)
                for c in (data or [])
                if isinstance(c, dict)
            ]
        except Exception as exc:
            log.warning("github.get_commits failed repo=%s: %s", repo, exc)
            return []

    def _parse_commit(self, raw: dict) -> CommitSummary:
        commit = raw.get("commit") or {}
        author_info = commit.get("author") or {}
        committer_node = raw.get("committer") or {}
        sha = raw.get("sha") or ""
        ts_str = author_info.get("date") or ""
        return CommitSummary(
            sha=sha,
            short_sha=sha[:7],
            author=committer_node.get("login") or author_info.get("name") or "unknown",
            author_email=author_info.get("email"),
            message=(commit.get("message") or "").split("\n")[0][:200],
            timestamp=_parse_dt(ts_str),
            url=raw.get("html_url"),
        )

    # ------------------------------------------------------------------
    # Pull Requests (merged only)
    # ------------------------------------------------------------------

    async def get_merged_prs(
        self,
        repo: str,
        since: datetime,
        until: datetime,
        base: str = "main",
    ) -> list[PullRequestSummary]:
        """
        Return PRs merged to *base* branch in [since, until].
        Returns [] on any error.
        """
        try:
            data = await self._get(
                f"/repos/{repo}/pulls",
                params={
                    "state": "closed",
                    "base": base,
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": self._config.github_max_items_per_page,
                },
            )
            result = []
            for pr in (data or []):
                if not isinstance(pr, dict):
                    continue
                merged_at = _parse_dt_opt(pr.get("merged_at"))
                if merged_at is None:
                    continue  # not merged
                if merged_at < since or merged_at > until:
                    continue
                result.append(self._parse_pr(pr))
            return result
        except Exception as exc:
            log.warning("github.get_merged_prs failed repo=%s base=%s: %s", repo, base, exc)
            return []

    async def get_merged_prs_any_base(
        self,
        repo: str,
        since: datetime,
        until: datetime,
    ) -> list[PullRequestSummary]:
        """Try 'main' then 'master'; return whichever has results (or both)."""
        main_prs = await self.get_merged_prs(repo, since, until, base="main")
        master_prs = await self.get_merged_prs(repo, since, until, base="master")
        # De-dup by PR number
        seen: set[int] = set()
        result = []
        for pr in main_prs + master_prs:
            if pr.number not in seen:
                seen.add(pr.number)
                result.append(pr)
        return result

    def _parse_pr(self, raw: dict) -> PullRequestSummary:
        user = raw.get("user") or {}
        labels = [
            lbl.get("name", "")
            for lbl in (raw.get("labels") or [])
            if isinstance(lbl, dict)
        ]
        head = raw.get("head") or {}
        base = raw.get("base") or {}
        return PullRequestSummary(
            number=raw.get("number") or 0,
            title=raw.get("title") or "",
            state=raw.get("state") or "closed",
            author=user.get("login") or "unknown",
            merged_at=_parse_dt_opt(raw.get("merged_at")),
            created_at=_parse_dt(raw.get("created_at") or ""),
            updated_at=_parse_dt_opt(raw.get("updated_at")),
            url=raw.get("html_url") or "",
            merge_commit_sha=raw.get("merge_commit_sha"),
            changed_files=raw.get("changed_files") or 0,
            labels=labels,
            head_ref=head.get("ref"),
            base_ref=base.get("ref"),
        )

    # ------------------------------------------------------------------
    # Changed files (compare two commits)
    # ------------------------------------------------------------------

    async def get_changed_files(
        self,
        repo: str,
        base_sha: str,
        head_sha: str,
    ) -> list[ChangedFileSummary]:
        """
        Return files changed between base_sha and head_sha via /compare.
        Returns [] on error or if the SHA range is trivial.
        """
        if not base_sha or not head_sha or base_sha == head_sha:
            return []
        try:
            data = await self._get(
                f"/repos/{repo}/compare/{base_sha}...{head_sha}"
            )
            return [
                self._parse_file(f)
                for f in (data.get("files") or [])
                if isinstance(f, dict)
            ]
        except Exception as exc:
            log.warning(
                "github.get_changed_files failed repo=%s: %s", repo, exc
            )
            return []

    def _parse_file(self, raw: dict) -> ChangedFileSummary:
        return ChangedFileSummary(
            filename=raw.get("filename") or "",
            status=raw.get("status") or "modified",
            additions=raw.get("additions") or 0,
            deletions=raw.get("deletions") or 0,
            blob_url=raw.get("blob_url"),
        )

    # ------------------------------------------------------------------
    # Releases / tags (deploy markers)
    # ------------------------------------------------------------------

    async def get_recent_releases(
        self,
        repo: str,
        since: datetime,
        until: datetime,
    ) -> list[DeployEvent]:
        """
        Return GitHub Releases published in [since, until].
        Returns [] on error.
        """
        try:
            data = await self._get(
                f"/repos/{repo}/releases",
                params={"per_page": self._config.github_max_items_per_page},
            )
            result = []
            for rel in (data or []):
                if not isinstance(rel, dict):
                    continue
                published = _parse_dt_opt(rel.get("published_at"))
                if published is None or published < since or published > until:
                    continue
                author = rel.get("author") or {}
                tag = rel.get("tag_name") or ""
                body = rel.get("body") or ""
                result.append(
                    DeployEvent(
                        id=f"release-{rel.get('id', tag)}",
                        kind="release",
                        ref=tag,
                        timestamp=published,
                        title=rel.get("name") or tag,
                        url=rel.get("html_url"),
                        author=author.get("login"),
                        image_tag_hint=_extract_image_hint(body, tag),
                        config_version_hint=_extract_version_hint(body, tag),
                    )
                )
            return result
        except Exception as exc:
            log.warning("github.get_recent_releases failed repo=%s: %s", repo, exc)
            return []

    def deploy_events_from_prs(
        self,
        prs: list[PullRequestSummary],
    ) -> list[DeployEvent]:
        """
        Synthesise DeployEvent objects from merged PRs when no Releases exist.

        Every merged PR is treated as a potential deploy marker.
        PRs with deploy-flavoured labels or branch names are still plain
        ``pr_merge`` kind — callers can filter by label if needed.
        """
        result = []
        for pr in prs:
            if pr.merged_at is None:
                continue
            result.append(
                DeployEvent(
                    id=f"pr-merge-{pr.number}",
                    kind="pr_merge",
                    ref=pr.head_ref or f"pr/{pr.number}",
                    timestamp=pr.merged_at,
                    title=f"PR #{pr.number}: {pr.title}",
                    url=pr.url,
                    commit_sha=pr.merge_commit_sha,
                    author=pr.author,
                )
            )
        return result
