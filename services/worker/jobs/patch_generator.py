"""
LLM-powered Kubernetes manifest patch generator.

Given an incident + current manifest YAML, asks the LLM to produce
a minimally-modified version targeting the root cause.
Falls back to a regex-based memory-bump if the LLM is unavailable.
"""

import os
import re

import httpx
import structlog

log = structlog.get_logger()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Maps known service names → manifest file paths in the repo
_SERVICE_MANIFEST_MAP: dict[str, str] = {
    "selfops-demo-app": "k8s/demo-app/deployment.yaml",
    "selfops-api": "k8s/platform/api-deployment.yaml",
    "selfops-worker": "k8s/platform/worker-deployment.yaml",
    "selfops-frontend": "k8s/platform/frontend-deployment.yaml",
    "selfops-analysis": "k8s/platform/analysis-service-deployment.yaml",
}


def resolve_manifest_path(service_name: str) -> str:
    return _SERVICE_MANIFEST_MAP.get(
        service_name,
        f"k8s/platform/{service_name}-deployment.yaml",
    )


async def generate_patch(
    incident_title: str,
    service_name: str,
    alert_name: str,
    analysis_summary: str,
    probable_cause: str,
    current_manifest: str,
) -> dict:
    """
    Returns:
        new_content    : str   — full modified YAML to commit
        description    : str   — one-line summary of the change
        commit_message : str
        pr_title       : str
        pr_body        : str
    """
    if not OPENROUTER_API_KEY:
        log.warning("OPENROUTER_API_KEY not set, using template patch")
        return _template_patch(alert_name, current_manifest, analysis_summary)

    prompt = (
        "You are a Kubernetes SRE fixing a production incident. "
        "Make ONE targeted change to the manifest below to address the root cause.\n\n"
        f"INCIDENT: {incident_title}\n"
        f"SERVICE:  {service_name}\n"
        f"ALERT:    {alert_name}\n"
        f"ANALYSIS: {analysis_summary}\n"
        f"ROOT CAUSE: {probable_cause}\n\n"
        "CURRENT MANIFEST:\n"
        f"```yaml\n{current_manifest[:3000]}\n```\n\n"
        "Fix guidelines (pick the most appropriate ONE):\n"
        "- High memory / OOM kills → increase memory limit by 50%\n"
        "- CPU throttling → increase CPU limit by 50%\n"
        "- Crash-looping, no resource issue → increase liveness probe initialDelaySeconds\n"
        "- Insufficient capacity → add 1 replica (only if current replicas < 3)\n\n"
        "Rules:\n"
        "- Change exactly ONE value.\n"
        "- Do NOT reformat, reorder, or add comments.\n"
        "- Return ONLY the complete modified YAML file. No markdown fences, no explanation."
    )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://github.com/selfops",
                    "X-Title": "SelfOps",
                },
                json={
                    "model": "anthropic/claude-3-haiku",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens": 4096,
                },
            )
            resp.raise_for_status()
            new_yaml = resp.json()["choices"][0]["message"]["content"].strip()

        # Strip accidental markdown fences
        if new_yaml.startswith("```"):
            lines = new_yaml.splitlines()
            new_yaml = "\n".join(
                lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            )

        if not new_yaml.strip():
            raise ValueError("LLM returned empty content")

        description = _describe_change(current_manifest, new_yaml, alert_name)
        log.info("patch generated via LLM", service=service_name, description=description)

    except Exception as exc:
        log.warning("LLM patch generation failed, using template", error=str(exc))
        return _template_patch(alert_name, current_manifest, analysis_summary)

    return _build_result(new_yaml, description, service_name, alert_name,
                         incident_title, analysis_summary, probable_cause)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _template_patch(alert_name: str, manifest: str, summary: str) -> dict:
    """Fallback: bump every memory limit by 50%."""
    new_manifest = _bump_memory_limits(manifest, factor=1.5)
    description = "increase memory limits by 50% to prevent OOM crashes"
    return _build_result(
        new_manifest, description, "service", alert_name,
        alert_name, summary, "Resource exhaustion (template fallback)",
    )


def _bump_memory_limits(manifest: str, factor: float = 1.5) -> str:
    """Regex-replace all 'memory: NNNMi/Gi' with factor-bumped values."""
    def replacer(m: re.Match) -> str:
        value, unit = int(m.group(1)), m.group(2)
        if unit == "Gi":
            new_val = round(value * factor, 1)
            return f"memory: {new_val}Gi"
        return f"memory: {int(value * factor)}Mi"

    return re.sub(r"memory:\s*(\d+)(Mi|Gi)", replacer, manifest)


def _describe_change(old: str, new: str, alert_name: str) -> str:
    old_set = set(old.splitlines())
    new_set = set(new.splitlines())
    added = [l.strip() for l in (new_set - old_set) if l.strip()]
    if added:
        return f"update resource config: {'; '.join(added[:2])}"
    return f"adjust k8s configuration to address {alert_name}"


def _build_result(
    new_content: str,
    description: str,
    service_name: str,
    alert_name: str,
    incident_title: str,
    analysis_summary: str,
    probable_cause: str,
) -> dict:
    pr_body = (
        "## Automated Fix — SelfOps GitOps Remediation\n\n"
        f"### Incident\n{incident_title}\n\n"
        f"### AI Analysis\n{analysis_summary}\n\n"
        f"### Root Cause\n{probable_cause}\n\n"
        f"### Change\n{description}\n\n"
        "---\n"
        "*Generated by SelfOps agentic remediation engine.*  \n"
        "*After merging, the verification agent will monitor the service for 5 minutes "
        "before marking the incident RESOLVED.*"
    )
    return {
        "new_content": new_content,
        "description": description,
        "commit_message": f"fix({service_name}): {description}",
        "pr_title": f"fix: {description} [{service_name}]",
        "pr_body": pr_body,
    }
