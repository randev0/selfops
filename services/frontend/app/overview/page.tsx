"use client"

import Link from "next/link"
import { AlertTriangle, Zap, Server, Wrench, Clock } from "lucide-react"
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts"
import { KpiCard } from "@/components/dashboard/kpi-card"
import { IncidentTrendChart } from "@/components/dashboard/incident-trend-chart"
import { ResourceChart } from "@/components/dashboard/resource-chart"
import { SeverityBadge } from "@/components/ui/severity-badge"
import { StatusBadge } from "@/components/ui/status-badge"
import { Header } from "@/components/layout/header"
import {
  mockIncidents,
  mockRemediations,
  mockServicesAtRisk,
  mockIncidentTrend,
} from "@/lib/mock-data"
import { formatRelativeTime } from "@/lib/utils"

const severityDistribution = [
  { name: "Critical", value: 3, color: "#ef4444" },
  { name: "High", value: 2, color: "#f97316" },
  { name: "Medium", value: 2, color: "#eab308" },
  { name: "Low", value: 1, color: "#3b82f6" },
]

const totalIncidents = severityDistribution.reduce((s, d) => s + d.value, 0)

interface DonutTooltipProps {
  active?: boolean
  payload?: Array<{ name: string; value: number; payload: { color: string } }>
}

function DonutTooltip({ active, payload }: DonutTooltipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p style={{ color: payload[0].payload.color }} className="font-semibold">
        {payload[0].name}: {payload[0].value}
      </p>
    </div>
  )
}

const trendData = mockIncidentTrend.map((d) => d.incidents)
const activeIncidents = mockIncidents.filter(
  (i) => i.status !== "resolved" && i.status !== "failed_remediation"
)
const criticalAlerts = mockIncidents.filter((i) => i.severity === "critical").length
const unhealthyWorkloads = 4
const remediationsToday = mockRemediations.length

export default function OverviewPage() {
  return (
    <div className="flex flex-col min-h-full">
      <Header title="Overview" />
      <div className="flex-1 p-6 space-y-6">
        {/* Row 1: KPI cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            title="Active Incidents"
            value={activeIncidents.length}
            delta="+2 from yesterday"
            deltaType="up"
            icon={AlertTriangle}
            iconColor="text-orange-400"
            trend={trendData.slice(-12)}
          />
          <KpiCard
            title="Critical Alerts"
            value={criticalAlerts}
            delta="+1 from yesterday"
            deltaType="up"
            icon={Zap}
            iconColor="text-red-400"
            trend={trendData.slice(-12).map((v) => Math.round(v * 0.4))}
          />
          <KpiCard
            title="Unhealthy Workloads"
            value={unhealthyWorkloads}
            delta="-1 from yesterday"
            deltaType="down"
            icon={Server}
            iconColor="text-yellow-400"
          />
          <KpiCard
            title="Remediations Today"
            value={remediationsToday}
            delta="3 successful"
            deltaType="neutral"
            icon={Wrench}
            iconColor="text-green-400"
          />
        </div>

        {/* Row 2: Incident trend + severity distribution */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <IncidentTrendChart />
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="mb-4">
              <h3 className="text-sm font-semibold text-zinc-100">Severity Distribution</h3>
              <p className="text-xs text-zinc-500 mt-0.5">All active incidents</p>
            </div>
            <div className="relative">
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie
                    data={severityDistribution}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={70}
                    paddingAngle={3}
                    dataKey="value"
                    startAngle={90}
                    endAngle={-270}
                  >
                    {severityDistribution.map((entry, i) => (
                      <Cell key={i} fill={entry.color} opacity={0.85} />
                    ))}
                  </Pie>
                  <Tooltip content={<DonutTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              {/* Center label */}
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <span className="text-2xl font-bold text-zinc-50">{totalIncidents}</span>
                <span className="text-xs text-zinc-500">total</span>
              </div>
            </div>
            {/* Legend */}
            <div className="mt-2 grid grid-cols-2 gap-1.5">
              {severityDistribution.map((d) => (
                <div key={d.name} className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: d.color }} />
                  <span className="text-xs text-zinc-400">{d.name}</span>
                  <span className="ml-auto text-xs font-semibold text-zinc-300">{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Row 3: Resource usage + Services at risk */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <ResourceChart />

          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="mb-4">
              <h3 className="text-sm font-semibold text-zinc-100">Services at Risk</h3>
              <p className="text-xs text-zinc-500 mt-0.5">Services with active incidents</p>
            </div>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th className="text-left py-2 text-zinc-500 font-medium">Service</th>
                  <th className="text-left py-2 text-zinc-500 font-medium hidden sm:table-cell">Namespace</th>
                  <th className="text-left py-2 text-zinc-500 font-medium">Risk</th>
                  <th className="text-right py-2 text-zinc-500 font-medium">Incidents</th>
                  <th className="text-right py-2 text-zinc-500 font-medium hidden md:table-cell">Last</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {mockServicesAtRisk.map((s) => (
                  <tr key={s.name} className="hover:bg-zinc-800/30 transition-colors">
                    <td className="py-2.5 font-mono font-medium text-zinc-200">{s.name}</td>
                    <td className="py-2.5 text-zinc-500 hidden sm:table-cell">{s.namespace}</td>
                    <td className="py-2.5">
                      <SeverityBadge severity={s.riskLevel} />
                    </td>
                    <td className="py-2.5 text-right text-zinc-300 font-semibold">
                      {s.activeIncidents}
                    </td>
                    <td className="py-2.5 text-right text-zinc-600 hidden md:table-cell">
                      {formatRelativeTime(s.lastIncidentAt)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Row 4: Recent incidents + recent remediations */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Recent Incidents */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-zinc-100">Recent Incidents</h3>
              <Link href="/incidents" className="text-xs text-blue-400 hover:text-blue-300 transition-colors">
                View all →
              </Link>
            </div>
            <div className="space-y-1">
              {mockIncidents.slice(0, 5).map((incident) => (
                <Link
                  key={incident.id}
                  href={`/incidents/${incident.id}`}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-zinc-800/50 transition-colors group"
                >
                  <SeverityBadge severity={incident.severity} />
                  <span className="flex-1 min-w-0 text-xs text-zinc-300 font-medium truncate group-hover:text-zinc-100 transition-colors">
                    {incident.title}
                  </span>
                  <span className="text-[10px] text-zinc-600 font-mono shrink-0">
                    {incident.service}
                  </span>
                  <span className="text-[10px] text-zinc-600 shrink-0">
                    {formatRelativeTime(incident.createdAt)}
                  </span>
                </Link>
              ))}
            </div>
          </div>

          {/* Recent Remediations */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-zinc-100">Recent Remediations</h3>
              <Link href="/remediations" className="text-xs text-blue-400 hover:text-blue-300 transition-colors">
                View all →
              </Link>
            </div>
            <div className="space-y-2">
              {mockRemediations.slice(0, 3).map((rem) => (
                <div
                  key={rem.id}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-zinc-800/30"
                >
                  <div
                    className={`h-2 w-2 rounded-full shrink-0 ${
                      rem.status === "success"
                        ? "bg-green-400"
                        : rem.status === "failed"
                        ? "bg-red-400"
                        : "bg-yellow-400 animate-pulse"
                    }`}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-zinc-200 truncate">{rem.actionName}</p>
                    <p className="text-[10px] text-zinc-600 font-mono">{rem.service}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-[10px] text-zinc-500">{rem.triggeredBy}</p>
                    <div className="flex items-center gap-1 justify-end mt-0.5">
                      <Clock className="h-2.5 w-2.5 text-zinc-600" />
                      <span className="text-[10px] text-zinc-600">{rem.duration}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
