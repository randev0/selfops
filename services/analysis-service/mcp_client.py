"""
HTTP client for the SelfOps MCP server REST bridge.

The analysis agent calls Prometheus and Loki through the MCP server
rather than directly, keeping data-fetching logic decoupled from the
agent runtime. The MCP server also exposes an SSE endpoint for any
MCP-native client that wants to connect.
"""

import os

import httpx
import structlog

log = structlog.get_logger()

MCP_SERVER_URL = os.environ.get(
    "MCP_SERVER_URL",
    "http://selfops-mcp.platform.svc.cluster.local:3001",
)


def call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """
    Call a tool on the MCP server via the REST bridge endpoint.

    Args:
        tool_name: The registered MCP tool name (e.g. 'fetch_prometheus_metrics').
        arguments: Dict of arguments to pass to the tool.

    Returns the tool's text output, or an error string on failure.
    """
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                f"{MCP_SERVER_URL}/api/tools/{tool_name}",
                json=arguments,
            )
            resp.raise_for_status()
            return resp.json().get("result", "No result returned from MCP server.")
    except httpx.HTTPStatusError as exc:
        log.warning("MCP tool call HTTP error", tool=tool_name, status=exc.response.status_code)
        return f"MCP tool '{tool_name}' returned HTTP {exc.response.status_code}"
    except Exception as exc:
        log.warning("MCP tool call failed", tool=tool_name, error=str(exc))
        return f"MCP call failed ({tool_name}): {exc}"
