"use client"

import Link from "next/link"
import { ChevronRight, Zap } from "lucide-react"
import { SeverityBadge } from "@/components/ui/severity-badge"
import { StatusBadge } from "@/components/ui/status-badge"
import { formatRelativeTime } from "@/lib/utils"
import { type Incident } from "@/lib/api"

interface IncidentsTableProps {
  incidents: Incident[]
}

export function IncidentsTable({ incidents }: IncidentsTableProps) {
  if (incidents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="h-12 w-12 rounded-full bg-zinc-800 flex items-center justify-center mb-4">
          <Zap className="h-6 w-6 text-zinc-600" />
        </div>
        <p className="text-sm font-medium text-zinc-400">No incidents found</p>
        <p className="text-xs text-zinc-600 mt-1">Try adjusting your filters</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 sticky top-0 bg-zinc-950/90 backdrop-blur-sm z-10">
            <th className="text-left px-4 py-3 text-xs font-medium text-zinc-500 uppercase tracking-wider w-8">
              <span className="sr-only">Severity</span>
            </th>
            <th className="text-left px-4 py-3 text-xs font-medium text-zinc-500 uppercase tracking-wider">
              Title
            </th>
            <th className="text-left px-4 py-3 text-xs font-medium text-zinc-500 uppercase tracking-wider hidden md:table-cell">
              Service
            </th>
            <th className="text-left px-4 py-3 text-xs font-medium text-zinc-500 uppercase tracking-wider hidden lg:table-cell">
              Namespace
            </th>
            <th className="text-left px-4 py-3 text-xs font-medium text-zinc-500 uppercase tracking-wider">
              Status
            </th>
            <th className="text-left px-4 py-3 text-xs font-medium text-zinc-500 uppercase tracking-wider hidden xl:table-cell">
              Created
            </th>
            <th className="text-left px-4 py-3 text-xs font-medium text-zinc-500 uppercase tracking-wider hidden xl:table-cell">
              Last Seen
            </th>
            <th className="w-8 px-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/50">
          {incidents.map((incident, i) => (
            <tr
              key={incident.id}
              className={`group hover:bg-zinc-800/30 transition-colors ${
                i % 2 === 0 ? "bg-zinc-900/30" : "bg-transparent"
              }`}
            >
              <td className="px-4 py-3">
                <SeverityBadge severity={incident.severity ?? "unknown"} />
              </td>

              <td className="px-4 py-3 max-w-xs">
                <Link
                  href={`/incidents/${incident.id}`}
                  className="font-medium text-zinc-100 hover:text-blue-400 transition-colors truncate block"
                >
                  {incident.title}
                </Link>
              </td>

              <td className="px-4 py-3 hidden md:table-cell">
                <span className="font-mono text-xs text-zinc-400">
                  {incident.service_name ?? "—"}
                </span>
              </td>

              <td className="px-4 py-3 hidden lg:table-cell">
                <span className="text-xs text-zinc-500">{incident.namespace ?? "—"}</span>
              </td>

              <td className="px-4 py-3">
                <StatusBadge status={incident.status ?? "open"} />
              </td>

              <td className="px-4 py-3 hidden xl:table-cell">
                <span className="text-xs text-zinc-500">
                  {formatRelativeTime(incident.created_at)}
                </span>
              </td>

              <td className="px-4 py-3 hidden xl:table-cell">
                <span className="text-xs text-zinc-500">
                  {formatRelativeTime(incident.last_seen_at)}
                </span>
              </td>

              <td className="px-2 py-3">
                <Link
                  href={`/incidents/${incident.id}`}
                  className="flex items-center justify-center h-6 w-6 rounded-md text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800 transition-colors opacity-0 group-hover:opacity-100"
                >
                  <ChevronRight className="h-4 w-4" />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
