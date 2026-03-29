# GitHub Deploy Correlation

## Overview

The GitHub deploy correlation adapter enriches incidents with recent
deploy/change activity from a GitHub repository.  It runs automatically
as part of `enrich_incident` and stores the result as
`IncidentEvidence(evidence_type="deploy_correlation")`.

When deploy data is available, the incident timeline includes
`source="deploy"` events for each release/PR merge and an optional
regression-warning marker when the incident closely follows a recent
deploy.

If GitHub is unconfigured or unreachable, enrichment continues normally —
the adapter fails silently and the incident is not affected.

---

## Configuration

All settings are read from environment variables (or the `.env` file).

| Environment variable | Default | Description |
|---|---|---|
| `GITHUB_TOKEN` | `""` | Personal access token with `repo:read` scope. Empty = unauthenticated (public repos only, lower rate limit). |
| `GITHUB_DEFAULT_REPO` | `""` | `owner/repo` used for all services with no explicit mapping. If empty and no mapping matches, correlation is skipped. |
| `GITHUB_SERVICE_REPOS_JSON` | `""` | JSON dict mapping service names to repos. Supports `*` suffix as prefix wildcard. Example: `{"payment-worker":"org/payments","auth-*":"org/auth"}` |
| `GITHUB_CORRELATION_WINDOW_MINUTES` | `240` | Look-back window in minutes from incident timestamp (default 4 h). |
| `GITHUB_REGRESSION_THRESHOLD_MINUTES` | `60` | Flag `likely_regression=true` if most recent deploy was within this many minutes of the incident. |
| `GITHUB_MAX_ITEMS_PER_PAGE` | `30` | Max items fetched per GitHub API page (capped at 100). |
| `GITHUB_API_BASE_URL` | `https://api.github.com` | Override for GitHub Enterprise Server. |

### Minimal configuration (single repo)

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_DEFAULT_REPO=myorg/myrepo
```

### Per-service mapping

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_SERVICE_REPOS_JSON={"payment-worker":"myorg/payments","auth-service":"myorg/auth"}
GITHUB_DEFAULT_REPO=myorg/platform
```

### Kubernetes secret

```bash
kubectl create secret generic selfops-github \
  --from-literal=github-token=$GITHUB_TOKEN \
  -n platform --dry-run=client -o yaml | kubectl apply -f -
```

Reference in the worker deployment:

```yaml
env:
  - name: GITHUB_TOKEN
    valueFrom:
      secretKeyRef:
        name: selfops-github
        key: github-token
  - name: GITHUB_DEFAULT_REPO
    value: "myorg/myrepo"
```

---

## Correlation Rules

### Time Window

All data is fetched within `[incident_timestamp - window_minutes, incident_timestamp]`.
Items outside this window are discarded before computing correlation.

### Deploy Events

Deploy events are identified by:

1. **GitHub Releases** — if any releases were published in the window, each is a `DeployEvent(kind="release")`.
2. **Merged PRs** — if no releases exist, every PR merged to the default branch (`main` or `master`) in the window becomes a `DeployEvent(kind="pr_merge")`.

### Regression Detection

```
likely_regression = True  iff  closest_deploy.timestamp ≥ (incident_timestamp − regression_threshold)
```

`closest_deploy` is the most recent `DeployEvent` strictly before the incident.
When `likely_regression` is `True`, the timeline includes a
`deploy.regression_suspected` event with `severity="warning"`.

### Changed Files

When there are ≥ 2 commits in the window, the adapter calls
`GET /repos/{repo}/compare/{oldest}...{newest}` to fetch changed files.
Up to 50 files are stored in `changed_files_sample`.

---

## Output Schema (`ChangeContext`)

Stored in `IncidentEvidence.content` as JSON.

```json
{
  "available": true,
  "error_message": null,
  "repo": "org/repo",
  "service": "payment-worker",
  "environment": "production",
  "incident_timestamp": "2025-03-01T14:00:00+00:00",
  "window_start": "2025-03-01T10:00:00+00:00",
  "window_end":   "2025-03-01T14:00:00+00:00",

  "recent_commits": [
    { "sha": "abc1234...", "short_sha": "abc1234", "author": "dev",
      "message": "fix: reduce memory usage", "timestamp": "...", "url": "..." }
  ],
  "recent_prs": [
    { "number": 42, "title": "feat: batch processor", "state": "closed",
      "author": "dev", "merged_at": "...", "url": "...",
      "merge_commit_sha": "abc1234", "changed_files": 7,
      "labels": ["backend"], "head_ref": "feat/batch", "base_ref": "main" }
  ],
  "recent_deploys": [
    { "id": "pr-merge-42", "kind": "pr_merge", "ref": "feat/batch",
      "timestamp": "2025-03-01T13:30:00+00:00",
      "title": "PR #42: feat: batch processor",
      "url": "https://github.com/org/repo/pull/42",
      "commit_sha": "abc1234", "author": "dev",
      "image_tag_hint": null, "config_version_hint": null }
  ],

  "likely_regression": true,
  "regression_window_minutes": 30,
  "closest_deploy": { "id": "pr-merge-42", ... },

  "changed_files_sample": [
    { "filename": "src/processor.py", "status": "modified",
      "additions": 12, "deletions": 3, "blob_url": "..." }
  ],
  "total_commits": 3,
  "total_prs_merged": 1
}
```

When `available = false`, all other fields are empty/null and `error_message`
explains why.

---

## Timeline Integration

Deploy events appear in `GET /api/incidents/{id}/timeline` as entries with
`source = "deploy"`.

| `event_type` | Trigger |
|---|---|
| `deploy.release` | A GitHub Release was published in the window |
| `deploy.pr_merge` | A PR was merged to the default branch |
| `deploy.direct_commit` | A direct push to the default branch (no PR) |
| `deploy.change` | Deploy event with an unrecognised kind |
| `deploy.regression_suspected` | Incident within regression threshold of closest deploy |

The `deploy.regression_suspected` event has `severity = "warning"` and
is timestamped at the incident time.

### Frontend rendering

The incident timeline component maps `source="deploy"` events as:
- `deploy.regression_suspected` → `alert` display type (orange, AlertTriangle icon)
- all other deploy events → `action` display type (yellow, Wrench icon)

---

## Files Changed

| File | Change |
|------|--------|
| `services/worker/github_correlation/__init__.py` | New — package entry point |
| `services/worker/github_correlation/models.py` | New — `CommitSummary`, `PullRequestSummary`, `DeployEvent`, `ChangedFileSummary`, `ChangeContext` |
| `services/worker/github_correlation/config.py` | New — `GitHubCorrelationConfig` (pydantic-settings) |
| `services/worker/github_correlation/adapter.py` | New — async GitHub REST adapter (read-only) |
| `services/worker/github_correlation/correlator.py` | New — `compute_correlation()` (pure) + `correlate_incident()` (I/O) |
| `services/worker/worker.py` | Modified — `enrich_incident` calls correlation, stores as `deploy_correlation` evidence |
| `services/api/app/timeline/models.py` | Modified — `"deploy"` added to `TimelineSource` |
| `services/api/app/timeline/aggregator.py` | Modified — `_from_deploy_correlation()` converter; `deploy_correlation` evidence routed to it |
| `services/frontend/lib/api.ts` | Modified — `"deploy"` in `ApiTimelineEvent.source`; `ChangeContext` and related TypeScript types |
| `services/frontend/app/incidents/[id]/page.tsx` | Modified — deploy source mapped in `apiTimelineToMock` |
| `tests/worker/conftest.py` | New |
| `tests/worker/test_github_correlation.py` | New — 36 unit tests |
| `tests/api/test_timeline_deploy.py` | New — 16 unit tests |
| `docs/github-correlation.md` | New — this file |

---

## Known Limitations

1. **No diff content** — only file names and change counts are stored; diff text is not fetched.
2. **PR base branch** — only `main` and `master` are tried; custom deployment branches (e.g. `production`) require setting `GITHUB_DEFAULT_REPO` and accepting that only pushes to `main`/`master` are detected.
3. **Rate limits** — unauthenticated requests are limited to 60/hour per IP; authenticated requests to 5000/hour. Set `GITHUB_TOKEN` in production.
4. **Single-repo per service** — the mapping is 1:1 (service → repo). Monorepos are supported via `GITHUB_DEFAULT_REPO` but all changed files across the repo are included, not filtered by service path.
5. **Image tag hints** — extracted via simple regex on release body text; not guaranteed to be accurate.
6. **No GitHub Actions integration** — workflow run data is not fetched; only commits, PRs, and releases.

---

## Follow-up Tasks

- Add `GITHUB_DEPLOYMENT_BRANCH` config option to target non-`main` branches.
- Filter `changed_files_sample` by service path prefix (for monorepos).
- Add GitHub Actions workflow run status as a `DeployEvent` source.
- Wire `ChangeContext` into the analysis service prompt so the LLM sees recent deploy context.
- Build a frontend "Recent Changes" panel on the incident detail page using `ChangeContext`.
- Add `GITHUB_REGRESSION_THRESHOLD_MINUTES` to the Kubernetes deployment manifest.
