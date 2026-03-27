"use client"

import { useState } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { ExternalLink, ChevronRight } from "lucide-react"
import { SeverityBadge } from "@/components/ui/severity-badge"
import { StatusBadge } from "@/components/ui/status-badge"
import { EvidenceSection } from "@/components/incident-detail/evidence-section"
import { AIAnalysisPanel } from "@/components/incident-detail/ai-analysis-panel"
import { RecommendedActions } from "@/components/incident-detail/recommended-actions"
import { IncidentTimeline } from "@/components/incident-detail/incident-timeline"
import { AuditSummaryCard } from "@/components/incident-detail/audit-summary"
import { Header } from "@/components/layout/header"
import { mockIncidents } from "@/lib/mock-data"
import { formatRelativeTime, formatAbsoluteTime, formatIncidentDuration } from "@/lib/utils"
import { cn } from "@/lib/utils"

type Tab = "evidence" | "timeline" | "related"

const relatedAlerts = [
  {
    name: "PodCrashLooping",
    labels: "namespace=platform, pod=payment-worker-xxx",
    fired: new Date(Date.now() - 1000 * 60 * 14).toISOString(),
  },
  {
    name: "HighMemoryUsage",
    labels: "namespace=platform, container=payment-worker",
    fired: new Date(Date.now() - 1000 * 60 * 13).toISOString(),
  },
]

export default function IncidentDetailPage() {
  const params = useParams()
  const id = params.id as string
  const [activeTab, setActiveTab] = useState<Tab>("evidence")

  const incident = mockIncidents.find((i) => i.id === id)

  if (!incident) {
    return (
      <div className="flex flex-col min-h-full">
        <Header title="Incidents" subtitle="Not Found" />
        <div className="flex-1 flex flex-col items-center justify-center gap-4 p-6">
          <div className="h-16 w-16 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
            <ChevronRight className="h-8 w-8 text-zinc-600" />
          </div>
          <div className="text-center">
            <h2 className="text-lg font-semibold text-zinc-100">Incident not found</h2>
            <p className="text-sm text-zinc-500 mt-1">
              The incident <span className="font-mono text-zinc-400">{id}</span> does not exist.
            </p>
          </div>
          <Link
            href="/incidents"
            className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
          >
            ← Back to incidents
          </Link>
        </div>
      </div>
    )
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: "evidence", label: "Evidence" },
    { key: "timeline", label: `Timeline (${incident.timeline.length})` },
    { key: "related", label: "Related Alerts" },
  ]

  return (
    <div className="flex flex-col min-h-full">
      <Header title="Incidents" subtitle={incident.service} />
      <div className="flex-1 flex min-h-0">
        {/* Main content */}
        <div className="flex-1 overflow-y-auto">
          <div className="p-6 space-y-5 max-w-4xl">
            {/* Breadcrumb */}
            <div className="flex items-center gap-1.5 text-xs text-zinc-500">
              <Link href="/incidents" className="hover:text-zinc-300 transition-colors">
                Incidents
              </Link>
              <ChevronRight className="h-3 w-3" />
              <span className="text-zinc-400 font-medium truncate max-w-xs">{incident.title}</span>
            </div>

            {/* Incident header card */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
              <h1 className="text-xl font-bold text-zinc-50 mb-3 leading-snug">
                {incident.title}
              </h1>
              <div className="flex flex-wrap items-center gap-2 mb-4">
                <SeverityBadge severity={incident.severity} />
                <StatusBadge status={incident.status} />
                <span className="font-mono text-xs text-zinc-400 bg-zinc-800 rounded px-2 py-0.5">
                  {incident.service}
                </span>
                <span className="text-xs text-zinc-500 bg-zinc-800/50 rounded px-2 py-0.5">
                  {incident.namespace}
                </span>
                <span
                  className={cn(
                    "text-xs rounded px-2 py-0.5 font-medium",
                    incident.environment === "production"
                      ? "bg-green-500/10 text-green-400"
                      : "bg-yellow-500/10 text-yellow-400"
                  )}
                >
                  {incident.environment}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-500">
                <span>
                  Created:{" "}
                  <span className="text-zinc-400">{formatAbsoluteTime(incident.createdAt)}</span>
                </span>
                <span>
                  Last seen:{" "}
                  <span className="text-zinc-400">{formatRelativeTime(incident.lastSeen)}</span>
                </span>
                <span>
                  Duration:{" "}
                  <span className="text-zinc-400">{formatIncidentDuration(incident.createdAt)}</span>
                </span>
                <a
                  href="#"
                  className="flex items-center gap-1 text-blue-400 hover:text-blue-300 transition-colors ml-auto"
                >
                  Open in Grafana
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            </div>

            {/* AI Summary card */}
            <div className="bg-zinc-900/50 border border-blue-500/10 rounded-xl p-5 bg-[radial-gradient(ellipse_at_top_left,_rgba(59,130,246,0.05)_0%,_transparent_60%)]">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-semibold text-blue-400 uppercase tracking-wider">
                  AI Summary
                </span>
              </div>
              <p className="text-sm text-zinc-300 leading-relaxed">{incident.summary}</p>
            </div>

            {/* Tabs */}
            <div>
              <div className="flex gap-1 border-b border-zinc-800 mb-5">
                {tabs.map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key)}
                    className={cn(
                      "px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
                      activeTab === tab.key
                        ? "border-blue-500 text-blue-400"
                        : "border-transparent text-zinc-500 hover:text-zinc-300"
                    )}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {activeTab === "evidence" && <EvidenceSection incident={incident} />}

              {activeTab === "timeline" && (
                <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
                  <IncidentTimeline incident={incident} />
                </div>
              )}

              {activeTab === "related" && (
                <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-zinc-800">
                        <th className="text-left px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider">
                          Alert Name
                        </th>
                        <th className="text-left px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider hidden md:table-cell">
                          Labels
                        </th>
                        <th className="text-left px-4 py-3 text-zinc-500 font-medium uppercase tracking-wider">
                          Fired
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800/50">
                      {relatedAlerts.map((alert) => (
                        <tr key={alert.name} className="hover:bg-zinc-800/30 transition-colors">
                          <td className="px-4 py-3 font-mono font-semibold text-zinc-200">
                            {alert.name}
                          </td>
                          <td className="px-4 py-3 text-zinc-500 hidden md:table-cell font-mono">
                            {alert.labels}
                          </td>
                          <td className="px-4 py-3 text-zinc-500">
                            {formatRelativeTime(alert.fired)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right sidebar */}
        <div className="w-80 shrink-0 overflow-y-auto border-l border-zinc-800 p-4 space-y-4 hidden lg:block">
          <AIAnalysisPanel incident={incident} />
          <RecommendedActions incident={incident} />
          <AuditSummaryCard incident={incident} />
        </div>
      </div>
    </div>
  )
}
