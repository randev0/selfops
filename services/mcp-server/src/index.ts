/**
 * SelfOps MCP Server
 *
 * Exposes Prometheus metrics and Loki logs as MCP resources and tools.
 * Also provides a REST bridge endpoint (/api/tools/:name) for the Python
 * analysis agent to call tools synchronously over plain HTTP.
 *
 * Transports:
 *   GET  /sse              – SSE stream for MCP-native clients
 *   POST /messages         – MCP message handler (paired with SSE session)
 *   POST /api/tools/:name  – REST bridge for Python agent
 *   GET  /health           – liveness probe
 */

import { McpServer, ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import express, { type Request, type Response } from "express";
import { z } from "zod";

const PROMETHEUS_URL =
  process.env.PROMETHEUS_URL ||
  "http://prometheus-operated.monitoring.svc.cluster.local:9090";
const LOKI_URL =
  process.env.LOKI_URL || "http://loki.monitoring.svc.cluster.local:3100";
const PORT = parseInt(process.env.PORT || "3001", 10);

// ---------------------------------------------------------------------------
// Core data-fetch functions (shared by MCP tools + REST bridge)
// ---------------------------------------------------------------------------

async function fetchPrometheusMetrics(query: string): Promise<string> {
  try {
    const url = `${PROMETHEUS_URL}/api/v1/query?query=${encodeURIComponent(query)}`;
    const resp = await fetch(url, { signal: AbortSignal.timeout(15_000) });
    if (!resp.ok) return `Prometheus error ${resp.status}: ${await resp.text().then(t => t.slice(0, 200))}`;

    const data = (await resp.json()) as {
      data?: { resultType?: string; result?: unknown[] };
    };
    const resultType = data.data?.resultType ?? "vector";
    const results = data.data?.result ?? [];

    if (!results.length) return "No data returned for this PromQL query.";

    if (resultType === "scalar") {
      const pair = results as [number, string];
      return `scalar: ${pair[1] ?? JSON.stringify(pair)}`;
    }

    const lines = (results as Array<{ metric: Record<string, string>; value: [number, string] }>)
      .slice(0, 15)
      .map((item) => {
        const labels = Object.entries(item.metric ?? {})
          .map(([k, v]) => `${k}="${v}"`)
          .join(", ");
        const value = item.value?.[1] ?? "N/A";
        return `${labels}: ${value}`;
      });
    return lines.join("\n");
  } catch (err) {
    return `Prometheus query failed: ${err}`;
  }
}

async function fetchLokiLogs(query: string, limit = 30): Promise<string> {
  try {
    const cleanQuery = query.replace(/^['"]|['"]$/g, "");
    const now = Date.now();
    const startNs = String((now - 10 * 60 * 1000) * 1_000_000);
    const endNs = String(now * 1_000_000);

    const params = new URLSearchParams({
      query: cleanQuery,
      limit: String(Math.min(limit, 50)),
      start: startNs,
      end: endNs,
      direction: "backward",
    });

    const resp = await fetch(`${LOKI_URL}/loki/api/v1/query_range?${params}`, {
      signal: AbortSignal.timeout(15_000),
    });
    if (!resp.ok)
      return `Loki error ${resp.status}: ${await resp.text().then(t => t.slice(0, 200))}`;

    const body = (await resp.json()) as {
      data?: { result?: Array<{ values: [string, string][] }> };
    };
    const streams = body.data?.result ?? [];
    const lines: string[] = [];
    for (const stream of streams) {
      for (const [, line] of stream.values ?? []) {
        lines.push(line);
      }
    }
    if (!lines.length) return "No log lines found for this query in the last 10 minutes.";
    return lines.slice(0, limit).join("\n");
  } catch (err) {
    return `Loki query failed: ${err}`;
  }
}

// ---------------------------------------------------------------------------
// MCP Server definition
// ---------------------------------------------------------------------------

const server = new McpServer({
  name: "selfops-data-server",
  version: "1.0.0",
});

// Tool: fetch_prometheus_metrics
server.tool(
  "fetch_prometheus_metrics",
  "Run a PromQL instant query against the cluster Prometheus. Returns a text table of metric labels → current value.",
  { query: z.string().describe("A valid PromQL expression") },
  async ({ query }) => ({
    content: [{ type: "text" as const, text: await fetchPrometheusMetrics(query) }],
  })
);

// Tool: fetch_loki_logs
server.tool(
  "fetch_loki_logs",
  "Fetch recent log lines from Loki using a LogQL stream selector. Returns the most recent matching lines.",
  {
    query: z.string().describe("A LogQL expression, e.g. '{namespace=\"platform\"} |= \"error\"'"),
    limit: z.number().optional().describe("Max lines to return (default 30, max 50)"),
  },
  async ({ query, limit }) => ({
    content: [{ type: "text" as const, text: await fetchLokiLogs(query, limit) }],
  })
);

// Resource: metrics://cpu-usage/{namespace}/{pod}
server.resource(
  "cpu-usage",
  new ResourceTemplate("metrics://cpu-usage/{namespace}/{pod}", { list: undefined }),
  async (uri, { namespace, pod }) => {
    const query = `rate(container_cpu_usage_seconds_total{namespace="${namespace}",pod="${pod}"}[5m])`;
    const text = await fetchPrometheusMetrics(query);
    return {
      contents: [{ uri: uri.href, mimeType: "text/plain", text }],
    };
  }
);

// Resource: k8s://pod-logs/{namespace}/{pod}
server.resource(
  "pod-logs",
  new ResourceTemplate("k8s://pod-logs/{namespace}/{pod}", { list: undefined }),
  async (uri, { namespace, pod }) => {
    const query = `{namespace="${namespace}", pod="${pod}"}`;
    const text = await fetchLokiLogs(query, 40);
    return {
      contents: [{ uri: uri.href, mimeType: "text/plain", text }],
    };
  }
);

// ---------------------------------------------------------------------------
// Express app: SSE transport + REST bridge
// ---------------------------------------------------------------------------

const app = express();
app.use(express.json());

// Active SSE sessions
const transports: Map<string, SSEServerTransport> = new Map();

// SSE endpoint — MCP-native clients connect here
app.get("/sse", async (req: Request, res: Response) => {
  const transport = new SSEServerTransport("/messages", res);
  transports.set(transport.sessionId, transport);
  res.on("close", () => transports.delete(transport.sessionId));
  await server.connect(transport);
});

// Message endpoint — pairs with the SSE session
app.post("/messages", async (req: Request, res: Response) => {
  const sessionId = req.query.sessionId as string;
  const transport = transports.get(sessionId);
  if (!transport) {
    res.status(404).json({ error: "MCP session not found" });
    return;
  }
  await transport.handlePostMessage(req, res);
});

// REST bridge — Python agent calls tools via plain HTTP POST
app.post("/api/tools/:name", async (req: Request, res: Response) => {
  const { name } = req.params;
  const args = req.body as Record<string, unknown>;

  let result: string;
  switch (name) {
    case "fetch_prometheus_metrics":
      result = await fetchPrometheusMetrics(String(args.query ?? ""));
      break;
    case "fetch_loki_logs":
      result = await fetchLokiLogs(
        String(args.query ?? ""),
        typeof args.limit === "number" ? args.limit : 30
      );
      break;
    default:
      res.status(404).json({ error: `Unknown tool: ${name}` });
      return;
  }
  res.json({ result });
});

// Health check
app.get("/health", (_req: Request, res: Response) => {
  res.json({ status: "ok", service: "selfops-mcp", version: "1.0.0" });
});

app.listen(PORT, () => {
  console.log(`SelfOps MCP server listening on :${PORT}`);
  console.log(`  Prometheus: ${PROMETHEUS_URL}`);
  console.log(`  Loki:       ${LOKI_URL}`);
});
