"use client"

import Link from "next/link"
import { Server, AlertTriangle, RotateCcw, Cpu } from "lucide-react"
import { KpiCard } from "@/components/dashboard/kpi-card"
import { Header } from "@/components/layout/header"
import { StatusBadge } from "@/components/ui/status-badge"
import { mockWorkloads } from "@/lib/mock-data"
import { formatRelativeTime, cn } from "@/lib/utils"

function ResourceBar({ value, className }: { value: number; className?: string }) {
  const color =
    value > 80 ? "bg-red-500" : value > 60 ? "bg-yellow-500" : "bg-green-500"
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden min-w-[40px]">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${Math.min(100, value)}%` }}
        />
      </div>
      <span
        className={cn(
          "text-xs font-mono font-medium w-8 text-right",
          value > 80 ? "text-red-400" : value > 60 ? "text-yellow-400" : "text-zinc-400"
        )}
      >
        {value}%
      </span>
    </div>
  )
}

function TypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    Deployment: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    StatefulSet: "bg-purple-500/10 text-purple-400 border-purple-500/20",
    DaemonSet: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
  }
  return (
    <span
      className={cn(
        "inline-flex text-[10px] font-semibold rounded px-1.5 py-0.5 border",
        colors[type] ?? "bg-zinc-500/10 text-zinc-400 border-zinc-500/20"
      )}
    >
      {type}
    </span>
  )
}

function WorkloadStatus({ status }: { status: string }) {
  const config: Record<string, { label: string; className: string }> = {
    healthy: { label: "Healthy", className: "bg-green-500/10 text-green-400" },
    degraded: { label: "Degraded", className: "bg-yellow-500/10 text-yellow-400" },
    critical: { label: "Critical", className: "bg-red-500/10 text-red-400" },
    unknown: { label: "Unknown", className: "bg-zinc-500/10 text-zinc-400" },
  }
  const c = config[status] ?? config.unknown
  return (
    <span className={cn("text-xs font-medium rounded-md px-2 py-0.5", c.className)}>
      {c.label}
    </span>
  )
}

export default function WorkloadsPage() {
  const total = mockWorkloads.length
  const unhealthy = mockWorkloads.filter((w) => w.status !== "healthy").length
  const restarting = mockWorkloads.filter((w) => w.restarts > 0).length
  const highResource = mockWorkloads.filter((w) => w.cpu > 70 || w.memory > 70).length

  return (
    <div className="flex flex-col min-h-full">
      <Header title="Workloads" />
      <div className="flex-1 p-6 space-y-6">
        {/* KPI cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            title="Total Workloads"
            value={total}
            icon={Server}
            iconColor="text-blue-400"
          />
          <KpiCard
            title="Unhealthy"
            value={unhealthy}
            delta={`${Math.round((unhealthy / total) * 100)}% of fleet`}
            deltaType="up"
            icon={AlertTriangle}
            iconColor="text-red-400"
          />
          <KpiCard
            title="Restarting"
            value={restarting}
            delta="pods with restarts > 0"
            deltaType="neutral"
            icon={RotateCcw}
            iconColor="text-yellow-400"
          />
          <KpiCard
            title="High Resource Usage"
            value={highResource}
            delta="CPU or memory > 70%"
            deltaType="neutral"
            icon={Cpu}
            iconColor="text-orange-400"
          />
        </div>

        {/* Workloads table */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-zinc-800">
            <h3 className="text-sm font-semibold text-zinc-100">All Workloads</h3>
            <p className="text-xs text-zinc-500 mt-0.5">
              {total} workloads across all namespaces
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-950/30">
                  <th className="text-left px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider">
                    Name
                  </th>
                  <th className="text-left px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider hidden md:table-cell">
                    Namespace
                  </th>
                  <th className="text-left px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider hidden lg:table-cell">
                    Type
                  </th>
                  <th className="text-left px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider hidden md:table-cell min-w-[120px]">
                    CPU
                  </th>
                  <th className="px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider hidden md:table-cell min-w-[120px]">
                    Memory
                  </th>
                  <th className="text-center px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider hidden lg:table-cell">
                    Restarts
                  </th>
                  <th className="text-center px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider">
                    Replicas
                  </th>
                  <th className="text-left px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider hidden xl:table-cell">
                    Node
                  </th>
                  <th className="text-left px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider hidden xl:table-cell">
                    Last Alert
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {mockWorkloads.map((wl, i) => (
                  <tr
                    key={wl.id}
                    className={cn(
                      "hover:bg-zinc-800/30 transition-colors",
                      i % 2 === 0 ? "bg-zinc-900/30" : "bg-transparent"
                    )}
                  >
                    {/* Name */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {wl.incidentId ? (
                          <Link
                            href={`/incidents/${wl.incidentId}`}
                            className="font-mono font-semibold text-zinc-200 hover:text-blue-400 transition-colors"
                          >
                            {wl.name}
                          </Link>
                        ) : (
                          <span className="font-mono font-semibold text-zinc-200">{wl.name}</span>
                        )}
                      </div>
                    </td>

                    {/* Namespace */}
                    <td className="px-4 py-3 text-zinc-500 hidden md:table-cell">{wl.namespace}</td>

                    {/* Type */}
                    <td className="px-4 py-3 hidden lg:table-cell">
                      <TypeBadge type={wl.type} />
                    </td>

                    {/* Status */}
                    <td className="px-4 py-3">
                      <WorkloadStatus status={wl.status} />
                    </td>

                    {/* CPU */}
                    <td className="px-4 py-3 hidden md:table-cell">
                      <ResourceBar value={wl.cpu} />
                    </td>

                    {/* Memory */}
                    <td className="px-4 py-3 hidden md:table-cell">
                      <ResourceBar value={wl.memory} />
                    </td>

                    {/* Restarts */}
                    <td className="px-4 py-3 text-center hidden lg:table-cell">
                      <span
                        className={cn(
                          "font-mono font-semibold",
                          wl.restarts > 5
                            ? "text-orange-400"
                            : wl.restarts > 0
                            ? "text-yellow-400"
                            : "text-zinc-600"
                        )}
                      >
                        {wl.restarts}
                      </span>
                    </td>

                    {/* Replicas */}
                    <td className="px-4 py-3 text-center">
                      <span
                        className={cn(
                          "font-mono text-xs font-semibold",
                          wl.readyReplicas < wl.replicas ? "text-red-400" : "text-zinc-400"
                        )}
                      >
                        {wl.readyReplicas}/{wl.replicas}
                      </span>
                    </td>

                    {/* Node */}
                    <td className="px-4 py-3 text-zinc-500 font-mono hidden xl:table-cell">
                      {wl.node}
                    </td>

                    {/* Last Alert */}
                    <td className="px-4 py-3 hidden xl:table-cell">
                      {wl.lastAlert ? (
                        <span className="text-zinc-500">{formatRelativeTime(wl.lastAlert)}</span>
                      ) : (
                        <span className="text-zinc-700">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
