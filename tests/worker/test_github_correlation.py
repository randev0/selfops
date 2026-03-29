"""
test_github_correlation.py
---------------------------
Unit tests for the GitHub deploy/change correlation adapter.

All tests are pure in-memory — no real HTTP calls are made.
The ``GitHubCorrelationAdapter`` is replaced with a ``FakeAdapter``
that returns canned data, keeping tests fast and hermetic.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from github_correlation.config import GitHubCorrelationConfig
from github_correlation.correlator import compute_correlation
from github_correlation.models import (
    ChangeContext,
    ChangedFileSummary,
    CommitSummary,
    DeployEvent,
    PullRequestSummary,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_INC_TS = datetime(2025, 3, 1, 14, 0, 0, tzinfo=timezone.utc)
_WINDOW = 240   # minutes
_THRESHOLD = 60  # minutes


def _dt(offset_minutes: int = 0) -> datetime:
    return _INC_TS + timedelta(minutes=offset_minutes)


def _commit(sha: str, offset_minutes: int) -> CommitSummary:
    return CommitSummary(
        sha=sha,
        short_sha=sha[:7],
        author="dev",
        message=f"fix: some change {sha[:4]}",
        timestamp=_dt(offset_minutes),
        url=f"https://github.com/org/repo/commit/{sha}",
    )


def _pr(number: int, merged_at_offset: int) -> PullRequestSummary:
    return PullRequestSummary(
        number=number,
        title=f"feat: PR {number}",
        state="closed",
        author="dev",
        merged_at=_dt(merged_at_offset),
        created_at=_dt(merged_at_offset - 60),
        url=f"https://github.com/org/repo/pull/{number}",
        merge_commit_sha=f"abc{number:04d}",
    )


def _deploy(id_: str, kind: str, offset_minutes: int) -> DeployEvent:
    return DeployEvent(
        id=id_,
        kind=kind,
        ref="main",
        timestamp=_dt(offset_minutes),
        title=f"Deploy {id_}",
        author="ci",
    )


def _file(name: str) -> ChangedFileSummary:
    return ChangedFileSummary(filename=name, status="modified")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# --------------------------------------------------------------------------- #
# compute_correlation — pure function tests
# --------------------------------------------------------------------------- #


def _correlate(**overrides) -> ChangeContext:
    defaults = dict(
        repo="org/repo",
        service="payment-worker",
        environment="production",
        incident_timestamp=_INC_TS,
        window_minutes=_WINDOW,
        regression_threshold_minutes=_THRESHOLD,
        commits=[],
        prs=[],
        deploys=[],
        changed_files=[],
    )
    defaults.update(overrides)
    return compute_correlation(**defaults)


class TestRegressionDetection:
    def test_incident_inside_deploy_window_sets_likely_regression(self):
        d = _deploy("d1", "release", -30)  # 30 min before incident
        ctx = _correlate(deploys=[d])
        assert ctx.likely_regression is True
        assert ctx.regression_window_minutes == 30

    def test_incident_outside_deploy_window_no_regression(self):
        d = _deploy("d1", "release", -90)  # 90 min before, threshold is 60
        ctx = _correlate(deploys=[d])
        assert ctx.likely_regression is False
        assert ctx.regression_window_minutes == 90

    def test_no_deploys_no_regression(self):
        ctx = _correlate(deploys=[])
        assert ctx.likely_regression is False
        assert ctx.closest_deploy is None
        assert ctx.regression_window_minutes is None

    def test_closest_deploy_is_most_recent_before_incident(self):
        d_old = _deploy("d-old", "release", -120)
        d_new = _deploy("d-new", "release", -20)
        ctx = _correlate(deploys=[d_old, d_new])
        assert ctx.closest_deploy is not None
        assert ctx.closest_deploy.id == "d-new"

    def test_deploy_exactly_at_threshold_is_regression(self):
        d = _deploy("d1", "pr_merge", -_THRESHOLD)  # exactly at threshold
        ctx = _correlate(deploys=[d])
        assert ctx.likely_regression is True

    def test_deploy_one_minute_over_threshold_is_not_regression(self):
        d = _deploy("d1", "pr_merge", -(_THRESHOLD + 1))
        ctx = _correlate(deploys=[d])
        assert ctx.likely_regression is False


class TestTimeWindowFiltering:
    def test_commits_outside_window_excluded(self):
        c_in = _commit("aaa111", -60)      # 60 min before incident, inside 240-min window
        c_out = _commit("bbb222", -300)    # 300 min before, outside 240-min window
        ctx = _correlate(commits=[c_in, c_out])
        shas = [c.sha for c in ctx.recent_commits]
        assert "aaa111" in shas
        assert "bbb222" not in shas

    def test_prs_outside_window_excluded(self):
        p_in = _pr(1, -60)
        p_out = _pr(2, -300)
        ctx = _correlate(prs=[p_in, p_out])
        numbers = [p.number for p in ctx.recent_prs]
        assert 1 in numbers
        assert 2 not in numbers

    def test_deploys_outside_window_excluded(self):
        d_in = _deploy("in", "release", -60)
        d_out = _deploy("out", "release", -300)
        ctx = _correlate(deploys=[d_in, d_out])
        ids = [d.id for d in ctx.recent_deploys]
        assert "in" in ids
        assert "out" not in ids

    def test_future_commits_excluded(self):
        c_future = _commit("fff000", +5)   # 5 min after incident
        ctx = _correlate(commits=[c_future])
        assert ctx.total_commits == 0

    def test_commit_exactly_at_window_start_included(self):
        c = _commit("exact", -_WINDOW)     # exactly at window boundary
        ctx = _correlate(commits=[c])
        assert ctx.total_commits == 1


class TestOrdering:
    def test_commits_sorted_newest_first(self):
        commits = [
            _commit("old111", -180),
            _commit("new222", -10),
            _commit("mid333", -90),
        ]
        ctx = _correlate(commits=commits)
        ts_list = [c.timestamp for c in ctx.recent_commits]
        assert ts_list == sorted(ts_list, reverse=True)

    def test_prs_sorted_by_merged_at_newest_first(self):
        prs = [_pr(3, -180), _pr(1, -10), _pr(2, -90)]
        ctx = _correlate(prs=prs)
        merged = [p.merged_at for p in ctx.recent_prs]
        assert merged == sorted(merged, reverse=True)

    def test_deploys_sorted_newest_first(self):
        deploys = [
            _deploy("d3", "release", -180),
            _deploy("d1", "release", -10),
            _deploy("d2", "release", -90),
        ]
        ctx = _correlate(deploys=deploys)
        ts_list = [d.timestamp for d in ctx.recent_deploys]
        assert ts_list == sorted(ts_list, reverse=True)


class TestDeduplication:
    def test_duplicate_commits_deduped(self):
        c = _commit("dup123", -30)
        ctx = _correlate(commits=[c, c, c])
        assert ctx.total_commits == 1

    def test_duplicate_prs_deduped(self):
        p = _pr(42, -30)
        ctx = _correlate(prs=[p, p])
        assert ctx.total_prs_merged == 1

    def test_duplicate_deploys_deduped(self):
        d = _deploy("dup", "release", -30)
        ctx = _correlate(deploys=[d, d, d])
        assert len(ctx.recent_deploys) == 1


class TestCounts:
    def test_total_counts_reflect_filtered_data(self):
        ctx = _correlate(
            commits=[_commit("a", -60), _commit("b", -300)],  # 1 in window
            prs=[_pr(1, -60), _pr(2, -300)],                  # 1 in window
        )
        assert ctx.total_commits == 1
        assert ctx.total_prs_merged == 1

    def test_empty_sources_gives_zero_counts(self):
        ctx = _correlate()
        assert ctx.total_commits == 0
        assert ctx.total_prs_merged == 0
        assert len(ctx.recent_deploys) == 0


class TestStructure:
    def test_available_true_on_success(self):
        ctx = _correlate()
        assert ctx.available is True

    def test_repo_service_environment_present(self):
        ctx = _correlate(service="svc", environment="staging")
        assert ctx.repo == "org/repo"
        assert ctx.service == "svc"
        assert ctx.environment == "staging"

    def test_window_timestamps_correct(self):
        ctx = _correlate()
        expected_start = _INC_TS - timedelta(minutes=_WINDOW)
        assert ctx.window_start == expected_start
        assert ctx.window_end == _INC_TS

    def test_changed_files_sample_stored(self):
        files = [_file(f"src/file{i}.py") for i in range(5)]
        ctx = _correlate(changed_files=files)
        assert len(ctx.changed_files_sample) == 5

    def test_changed_files_capped_at_50(self):
        files = [_file(f"f{i}.py") for i in range(100)]
        ctx = _correlate(changed_files=files)
        assert len(ctx.changed_files_sample) == 50


# --------------------------------------------------------------------------- #
# Config — repo_for_service
# --------------------------------------------------------------------------- #


class TestConfig:
    def test_exact_match(self):
        cfg = GitHubCorrelationConfig(
            github_service_repos_json='{"payment-worker":"org/payments"}',
        )
        assert cfg.repo_for_service("payment-worker") == "org/payments"

    def test_prefix_match(self):
        cfg = GitHubCorrelationConfig(
            github_service_repos_json='{"payment-*":"org/payments"}',
        )
        assert cfg.repo_for_service("payment-worker") == "org/payments"
        assert cfg.repo_for_service("payment-api") == "org/payments"

    def test_default_repo_fallback(self):
        cfg = GitHubCorrelationConfig(github_default_repo="org/monorepo")
        assert cfg.repo_for_service("unknown-svc") == "org/monorepo"

    def test_no_match_no_default_returns_none(self):
        cfg = GitHubCorrelationConfig()
        assert cfg.repo_for_service("unknown") is None

    def test_bad_json_service_repos_falls_back_to_default(self):
        cfg = GitHubCorrelationConfig(
            github_service_repos_json="not-valid-json",
            github_default_repo="org/fallback",
        )
        assert cfg.repo_for_service("any-service") == "org/fallback"

    def test_per_page_capped_at_100(self):
        cfg = GitHubCorrelationConfig(github_max_items_per_page=9999)
        assert cfg.github_max_items_per_page == 100


# --------------------------------------------------------------------------- #
# correlate_incident — integration with FakeAdapter
# --------------------------------------------------------------------------- #


class FakeAdapter:
    """
    Test double for GitHubCorrelationAdapter.
    Accepts commits/prs/releases lists to return; raises on configured failure.
    """

    def __init__(
        self,
        commits=None,
        prs=None,
        releases=None,
        files=None,
        raise_on: str | None = None,
    ):
        self._commits = commits or []
        self._prs = prs or []
        self._releases = releases or []
        self._files = files or []
        self._raise_on = raise_on

    async def get_commits(self, repo, since, until, sha="HEAD"):
        if self._raise_on == "commits":
            raise RuntimeError("simulated commits failure")
        return self._commits

    async def get_merged_prs_any_base(self, repo, since, until):
        if self._raise_on == "prs":
            raise RuntimeError("simulated prs failure")
        return self._prs

    async def get_recent_releases(self, repo, since, until):
        if self._raise_on == "releases":
            raise RuntimeError("simulated releases failure")
        return self._releases

    async def get_changed_files(self, repo, base_sha, head_sha):
        if self._raise_on == "files":
            return []
        return self._files

    def deploy_events_from_prs(self, prs):
        return [
            DeployEvent(
                id=f"pr-merge-{p.number}",
                kind="pr_merge",
                ref=p.head_ref or "main",
                timestamp=p.merged_at,
                title=f"PR #{p.number}: {p.title}",
                author=p.author,
            )
            for p in prs
            if p.merged_at
        ]

    async def close(self):
        pass


async def _correlate_with_fake(
    fake: FakeAdapter,
    config: GitHubCorrelationConfig,
    incident_timestamp: datetime = _INC_TS,
    service: str = "payment-worker",
    environment: str = "production",
) -> ChangeContext:
    """
    Patch correlate_incident to use FakeAdapter instead of real HTTP adapter.
    """
    from github_correlation import correlator as _corr_mod
    from github_correlation.correlator import _utc

    repo = config.repo_for_service(service)
    if not repo:
        return ChangeContext(
            available=False,
            error_message=f"No repo for {service}",
            service=service,
            environment=environment,
        )

    inc_ts = _utc(incident_timestamp)
    from datetime import timedelta

    window_start = inc_ts - timedelta(minutes=config.github_correlation_window_minutes)

    commits, prs, releases = await asyncio.gather(
        fake.get_commits(repo, since=window_start, until=inc_ts),
        fake.get_merged_prs_any_base(repo, since=window_start, until=inc_ts),
        fake.get_recent_releases(repo, since=window_start, until=inc_ts),
    )

    deploys = releases or fake.deploy_events_from_prs(prs)

    changed_files = []
    if len(commits) >= 2:
        changed_files = await fake.get_changed_files(
            repo, base_sha=commits[-1].sha, head_sha=commits[0].sha
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


class TestCorrelateWithFakeAdapter:
    def _cfg(self, **kwargs) -> GitHubCorrelationConfig:
        defaults = dict(
            github_default_repo="org/repo",
            github_correlation_window_minutes=240,
            github_regression_threshold_minutes=60,
        )
        defaults.update(kwargs)
        return GitHubCorrelationConfig(**defaults)

    def test_no_activity_returns_empty_available_context(self):
        cfg = self._cfg()
        ctx = _run(_correlate_with_fake(FakeAdapter(), cfg))
        assert ctx.available is True
        assert ctx.total_commits == 0
        assert ctx.total_prs_merged == 0
        assert ctx.likely_regression is False

    def test_deploy_30min_before_sets_regression(self):
        releases = [_deploy("r1", "release", -30)]
        cfg = self._cfg()
        ctx = _run(_correlate_with_fake(FakeAdapter(releases=releases), cfg))
        assert ctx.likely_regression is True
        assert ctx.regression_window_minutes == 30

    def test_deploy_from_pr_merge_when_no_releases(self):
        prs = [_pr(7, -45)]
        cfg = self._cfg()
        fake = FakeAdapter(prs=prs, releases=[])
        ctx = _run(_correlate_with_fake(fake, cfg))
        # deploy synthesised from PR merge
        assert len(ctx.recent_deploys) == 1
        assert ctx.recent_deploys[0].kind == "pr_merge"

    def test_changed_files_fetched_when_multiple_commits(self):
        commits = [_commit("aaa", -10), _commit("bbb", -30)]
        files = [_file("src/app.py"), _file("README.md")]
        fake = FakeAdapter(commits=commits, files=files)
        cfg = self._cfg()
        ctx = _run(_correlate_with_fake(fake, cfg))
        assert len(ctx.changed_files_sample) == 2

    def test_no_repo_configured_returns_unavailable(self):
        cfg = GitHubCorrelationConfig()  # no token, no default repo
        ctx = _run(
            _correlate_with_fake(FakeAdapter(), cfg, service="orphan-svc")
        )
        assert ctx.available is False
        assert "orphan-svc" in (ctx.error_message or "")

    def test_partial_failure_commits_ok_releases_fail(self):
        """When releases return empty, we fall back to PR-based deploys."""
        commits = [_commit("c1", -20)]
        prs = [_pr(5, -40)]
        fake = FakeAdapter(commits=commits, prs=prs, releases=[])
        cfg = self._cfg()
        ctx = _run(_correlate_with_fake(fake, cfg))
        assert ctx.total_commits == 1
        assert ctx.total_prs_merged == 1

