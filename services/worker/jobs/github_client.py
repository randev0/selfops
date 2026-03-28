"""
Async GitHub REST API client for GitOps remediation.

Requires env vars:
  GITHUB_TOKEN  — personal access token with 'repo' scope
  GITHUB_REPO   — owner/repo, e.g. 'randev0/selfops'
"""

import base64
import os

import httpx
import structlog

log = structlog.get_logger()

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "randev0/selfops")
_API = "https://api.github.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def get_default_branch_sha(branch: str = "main") -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{_API}/repos/{GITHUB_REPO}/git/refs/heads/{branch}",
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()["object"]["sha"]


async def create_branch(new_branch: str, base_branch: str = "main") -> str:
    sha = await get_default_branch_sha(base_branch)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_API}/repos/{GITHUB_REPO}/git/refs",
            headers=_headers(),
            json={"ref": f"refs/heads/{new_branch}", "sha": sha},
        )
        resp.raise_for_status()
    log.info("github branch created", branch=new_branch, repo=GITHUB_REPO)
    return new_branch


async def get_file(path: str, branch: str = "main") -> dict:
    """Returns {"content": str (decoded UTF-8), "sha": str}."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{_API}/repos/{GITHUB_REPO}/contents/{path}",
            headers=_headers(),
            params={"ref": branch},
        )
        resp.raise_for_status()
        data = resp.json()
        # GitHub base64-encodes with newlines — decode cleanly
        content = base64.b64decode(data["content"].replace("\n", "")).decode("utf-8")
        return {"content": content, "sha": data["sha"]}


async def commit_file(
    branch: str,
    path: str,
    new_content: str,
    message: str,
    file_sha: str,
) -> dict:
    """Commit a file update to an existing branch."""
    encoded = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.put(
            f"{_API}/repos/{GITHUB_REPO}/contents/{path}",
            headers=_headers(),
            json={
                "message": message,
                "content": encoded,
                "sha": file_sha,
                "branch": branch,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def create_pull_request(
    branch: str,
    title: str,
    body: str,
    base: str = "main",
) -> dict:
    """Open a PR. Returns {"number": int, "html_url": str, "state": str}."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_API}/repos/{GITHUB_REPO}/pulls",
            headers=_headers(),
            json={"title": title, "body": body, "head": branch, "base": base},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "number": data["number"],
            "html_url": data["html_url"],
            "state": data["state"],
        }


async def get_pr_state(pr_number: int) -> str:
    """Returns 'open', 'closed', or 'merged'."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{_API}/repos/{GITHUB_REPO}/pulls/{pr_number}",
            headers=_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("merged"):
            return "merged"
        return data.get("state", "unknown")
