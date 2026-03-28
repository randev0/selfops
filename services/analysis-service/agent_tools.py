"""
LangChain tools for the ReAct investigation agent.

Prometheus and Loki queries are routed through the MCP server
(mcp_client.call_mcp_tool) to keep data-fetching decoupled from the
agent runtime. The Kubernetes resource tool still calls the in-cluster
API directly because the analysis-service pod holds the ServiceAccount.

Each tool is synchronous so LangChain's AgentExecutor can safely call
them in a thread pool when running under ainvoke().
"""

import json
import os

import httpx
import structlog
from langchain.tools import tool

from mcp_client import call_mcp_tool

log = structlog.get_logger()

_K8S_API = "https://kubernetes.default.svc"
_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

# Map lowercase kind -> API path template
_KIND_PATHS = {
    "deployment": "/apis/apps/v1/namespaces/{ns}/deployments/{name}",
    "replicaset": "/apis/apps/v1/namespaces/{ns}/replicasets/{name}",
    "pod": "/api/v1/namespaces/{ns}/pods/{name}",
    "service": "/api/v1/namespaces/{ns}/services/{name}",
    "configmap": "/api/v1/namespaces/{ns}/configmaps/{name}",
}


@tool
def fetch_prometheus_metrics(query: str, duration: str = "5m") -> str:
    """Run a PromQL instant query against Prometheus via the MCP server.

    Args:
        query: A valid PromQL expression, e.g.
            'kube_pod_container_status_restarts_total{namespace="platform"}'
            or 'rate(container_cpu_usage_seconds_total{namespace="platform"}[5m])'
        duration: Unused (reserved for future range queries). Keep as '5m'.

    Returns a text table of metric labels → current value, up to 15 series.
    Data is fetched through the SelfOps MCP server.
    """
    return call_mcp_tool("fetch_prometheus_metrics", {"query": query})


@tool
def fetch_loki_logs(query: str, limit: int = 30) -> str:
    """Fetch recent log lines from Loki via the MCP server.

    Args:
        query: A LogQL expression, e.g.
            '{namespace="platform"}' or
            '{app="selfops-demo-app"} |= "error"' or
            '{namespace="platform", pod=~"payment.*"}'
        limit: Maximum number of log lines to return (capped at 50).

    Returns the most recent log lines joined by newlines.
    Data is fetched through the SelfOps MCP server.
    """
    return call_mcp_tool("fetch_loki_logs", {"query": query, "limit": min(limit, 50)})


@tool
def get_k8s_resource_yaml(resource_path: str) -> str:
    """Fetch the live state of a Kubernetes resource from the cluster API.

    Args:
        resource_path: Slash-separated string in the format 'kind/name/namespace'.
            Examples:
              'deployment/selfops-demo-app/platform'
              'pod/selfops-demo-app-xyz-abc/platform'
            Supported kinds: deployment, replicaset, pod, service, configmap

    Returns a JSON summary of the resource's status, replicas, and conditions.
    Calls the k8s in-cluster API directly using the analysis-service ServiceAccount.
    """
    resource_path = resource_path.strip().strip("'\"")
    parts = resource_path.split("/")
    if len(parts) != 3:
        return (
            "Invalid format. Expected 'kind/name/namespace', "
            f"got: '{resource_path}'. "
            "Example: 'deployment/selfops-demo-app/platform'"
        )
    kind, name, namespace = parts
    kind_lower = kind.lower()
    path_template = _KIND_PATHS.get(kind_lower)
    if not path_template:
        supported = ", ".join(_KIND_PATHS.keys())
        return f"Unsupported kind '{kind}'. Supported kinds: {supported}"

    try:
        with open(_TOKEN_PATH) as f:
            token = f.read().strip()
    except FileNotFoundError:
        return "Not running in-cluster — no service account token found."

    url = _K8S_API + path_template.format(ns=namespace, name=name)
    try:
        with httpx.Client(verify=_CA_PATH, timeout=10.0) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {token}"})

        if resp.status_code == 404:
            return f"{kind}/{name} not found in namespace '{namespace}'."
        resp.raise_for_status()
        resource = resp.json()

    except Exception as exc:
        log.warning("get_k8s_resource_yaml failed", error=str(exc))
        return f"Kubernetes API call failed: {exc}"

    meta = resource.get("metadata", {})
    status = resource.get("status", {})
    spec = resource.get("spec", {})

    summary = {
        "name": meta.get("name"),
        "namespace": meta.get("namespace"),
        "labels": meta.get("labels", {}),
        "replicas_desired": spec.get("replicas"),
        "replicas_ready": status.get("readyReplicas"),
        "replicas_available": status.get("availableReplicas"),
        "conditions": status.get("conditions", []),
        "observed_generation": status.get("observedGeneration"),
    }
    return json.dumps(summary, indent=2, default=str)[:2000]
