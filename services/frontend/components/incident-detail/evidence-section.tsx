"use client"

import {
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip,
} from "recharts"
import { ExternalLink } from "lucide-react"
import { type Incident } from "@/lib/mock-data"

const cpuData = [
  { t: "02:38", v: 22 },
  { t: "02:39", v: 28 },
  { t: "02:40", v: 35 },
  { t: "02:41", v: 52 },
  { t: "02:42", v: 71 },
  { t: "02:43", v: 89 },
  { t: "02:44", v: 94 },
  { t: "02:45", v: 91 },
]

const logLines = [
  {
    ts: "02:41:03.114",
    level: "INFO",
    msg: "Starting transaction batch processing (queue_size=8192)",
    color: "text-zinc-400",
  },
  {
    ts: "02:41:04.221",
    level: "WARN",
    msg: "Memory usage at 78% — batch queue growing unbounded",
    color: "text-yellow-400",
  },
  {
    ts: "02:41:06.889",
    level: "ERROR",
    msg: "Failed to flush batch: connection pool exhausted (pool_size=50/50)",
    color: "text-red-400",
  },
  {
    ts: "02:41:07.003",
    level: "ERROR",
    msg: "Retry #1 failed — ConnectionPoolTimeoutError after 5000ms",
    color: "text-red-400",
  },
  {
    ts: "02:41:07.901",
    level: "ERROR",
    msg: "Retry #2 failed — ConnectionPoolTimeoutError after 5000ms",
    color: "text-red-400",
  },
  {
    ts: "02:41:08.114",
    level: "FATAL",
    msg: "Unhandled exception in batch worker — process exiting",
    color: "text-red-500",
  },
  {
    ts: "02:41:08.115",
    level: "INFO",
    msg: "Traceback: MemoryError at queue.append() — heap exhausted",
    color: "text-zinc-500",
  },
  {
    ts: "02:41:08.203",
    level: "INFO",
    msg: "Container killed by OOM killer (exit code 137)",
    color: "text-zinc-600",
  },
]

interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{ value: number }>
  label?: string
}

function MiniTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-zinc-400">{label}</p>
      <p className="text-zinc-100 font-semibold">{payload[0].value}%</p>
    </div>
  )
}

export function EvidenceSection({ incident }: { incident: Incident }) {
  return (
    <div className="grid grid-cols-1 gap-4">
      {/* Metric Snapshot */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-semibold text-zinc-100">
            CPU Usage — {incident.service}
          </h4>
          <span className="text-xs font-semibold bg-red-500/15 text-red-400 border border-red-500/20 rounded-md px-2 py-0.5">
            Peak: 94%
          </span>
        </div>
        <p className="text-xs text-zinc-500 mb-3">Last 7 minutes before incident</p>
        <ResponsiveContainer width="100%" height={120}>
          <LineChart data={cpuData} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
            <Line
              type="monotone"
              dataKey="v"
              stroke="#ef4444"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 3, fill: "#ef4444" }}
            />
            <Tooltip content={<MiniTooltip />} cursor={{ stroke: "#3f3f46" }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Logs Preview */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-semibold text-zinc-100">Log Lines</h4>
          <a
            href="#"
            className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            View in Loki
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
        <div className="bg-zinc-950 rounded-lg p-3 font-mono text-xs overflow-x-auto">
          {logLines.map((line, i) => (
            <div key={i} className="flex gap-2 leading-relaxed">
              <span className="text-zinc-600 shrink-0">{line.ts}</span>
              <span
                className={`shrink-0 font-semibold w-12 ${
                  line.level === "ERROR" || line.level === "FATAL"
                    ? "text-red-400"
                    : line.level === "WARN"
                    ? "text-yellow-400"
                    : "text-zinc-500"
                }`}
              >
                {line.level}
              </span>
              <span className={line.color}>{line.msg}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Kubernetes Signals */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <h4 className="text-sm font-semibold text-zinc-100 mb-3">Kubernetes Signals</h4>
        <div className="grid grid-cols-2 gap-2">
          {[
            { label: "Pod restarts", value: "14", status: "error" },
            { label: "OOMKilled", value: "14", status: "error" },
            { label: "Last restart", value: "2m ago", status: "warn" },
            { label: "Exit code", value: "137", status: "error" },
            { label: "Node", value: "node-2", status: "ok" },
            { label: "Image", value: "python:3.11-slim", status: "ok" },
          ].map((row) => (
            <div key={row.label} className="flex items-center justify-between bg-zinc-800/50 rounded-lg px-3 py-2">
              <span className="text-xs text-zinc-500">{row.label}</span>
              <span
                className={`text-xs font-mono font-semibold ${
                  row.status === "error"
                    ? "text-red-400"
                    : row.status === "warn"
                    ? "text-yellow-400"
                    : "text-zinc-300"
                }`}
              >
                {row.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
