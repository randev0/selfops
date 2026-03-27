import Link from "next/link"
import { type Incident } from "@/lib/mock-data"
import { formatRelativeTime } from "@/lib/utils"

interface AuditEvent {
  actor: string
  message: string
  timestamp: string
}

function getRecentAuditEvents(incident: Incident): AuditEvent[] {
  return incident.timeline
    .slice(-3)
    .reverse()
    .map((e) => ({
      actor: e.actor,
      message: e.message,
      timestamp: e.timestamp,
    }))
}

function getInitials(name: string): string {
  return name
    .split(/[\s-]/)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .slice(0, 2)
    .join("")
}

export function AuditSummaryCard({ incident }: { incident: Incident }) {
  const events = getRecentAuditEvents(incident)

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-zinc-100 mb-3">Recent Activity</h3>

      {events.length === 0 ? (
        <p className="text-xs text-zinc-500">No activity yet.</p>
      ) : (
        <div className="space-y-3">
          {events.map((event, i) => (
            <div key={i} className="flex items-start gap-2.5">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-700 border border-zinc-600 text-[9px] font-bold text-zinc-300 shrink-0">
                {getInitials(event.actor)}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-zinc-300 leading-relaxed truncate">{event.message}</p>
                <p className="text-[10px] text-zinc-600 mt-0.5">{formatRelativeTime(event.timestamp)}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 pt-3 border-t border-zinc-800">
        <Link
          href={`/audit`}
          className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
        >
          View full audit log →
        </Link>
      </div>
    </div>
  )
}
