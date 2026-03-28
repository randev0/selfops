"""
LangChain tools for the ReAct investigation agent.

Each tool is synchronous (uses httpx.Client) so that LangChain's AgentExecutor
can safely call them in a thread-pool when running under ainvoke().
"""

import json
import os
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from langchain.tools import tool

log = structlog.get_logger()

PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL",
    "http://prometheus-operated.monitoring.svc.cluster.local:9090",
)
LOKI_URL = os.environ.get(
    "LOKI_URL",
    "http://loki.monitoring.svc.cluster.local:3100",
)
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
    """Run a PromQL instant query against Prometheus.

    Args:
        query: A valid PromQL expression, e.g.
            'kube_pod_container_status_restarts_total{namespace="platform"}'
            or 'rate(container_cpu_usage_seconds_total{namespace="platform"}[5m])'
        duration: Unused (reserved for future range queries). Keep as '5m'.

    Returns a text table of metric labels → current value, up to 15 series.
    """
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
            )
            resp.raise_for_status()
            results = resp.json().get("data", {}).get("result", [])

        if not results:
            return "No data returned for this PromQL query."

        lines = []
        for item in results[:15]:
            metric = item.get("metric", {})
            value = item.get("value", [None, "N/A"])[1]
            label_str = ", ".join(f'{k}="{v}"' for k, v in metric.items())
            lines.append(f"{label_str}: {value}")
        return "\n".join(lines)

    except Exception as exc:
        log.warning("fetch_prometheus_metrics failed", error=str(exc))
        return f"Prometheus query failed: {exc}"


@tool
def fetch_loki_logs(query: str, limit: int = 30) -> str:
    """Fetch recent log lines from Loki using a LogQL stream selector.

    Args:
        query: A LogQL expression, e.g.
            '{namespace="platform"}' or
            '{app="selfops-demo-app"} |= "error"' or
            '{namespace="platform", pod=~"payment.*"}'
        limit: Maximum number of log lines to return (capped at 50).

    Returns the most recent log lines joined by newlines.
    """
    try:
        now = datetime.now(timezone.utc)
        start_ns = int((now - timedelta(minutes=10)).timestamp() * 1_000_000_000)
        end_ns = int(now.timestamp() * 1_000_000_000)

        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{LOKI_URL}/loki/api/v1/query_range",
                params={
                    "query": query,
                    "limit": min(limit, 50),
                    "start": start_ns,
                    "end": end_ns,
                    "direction": "backward",
                },
            )
            resp.raise_for_status()
            streams = resp.json().get("data", {}).get("result", [])

        lines = []
        for stream in streams:
            for _ts, line in stream.get("values", []):
                lines.append(line)

        if not lines:
            return "No log lines found for this query in the last 10 minutes."

        # Return at most `limit` most-recent lines
        return "\n".join(lines[:limit])

    except Exception as exc:
        log.warning("fetch_loki_logs failed", error=str(exc))
        return f"Loki query failed: {exc}"


@tool
def get_k8s_resource_yaml(kind: str, name: str, namespace: str) -> str:
    """Fetch the live state of a Kubernetes resource from the cluster API.

    Args:
        kind: Resource kind — one of: deployment, replicaset, pod, service, configmap
        name: Exact resource name (e.g. 'selfops-demo-app')
        namespace: Kubernetes namespace (e.g. 'platform')

    Returns a JSON summary of the resource's status, replicas, conditions,
    and labels. Truncated to 2000 characters.
    """
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
