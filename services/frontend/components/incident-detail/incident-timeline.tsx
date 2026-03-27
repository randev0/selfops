import {
  AlertTriangle,
  Search,
  Brain,
  Wrench,
  CheckCircle2,
} from "lucide-react"
import { type Incident } from "@/lib/mock-data"
import { formatRelativeTime } from "@/lib/utils"
import { cn } from "@/lib/utils"

const typeConfig = {
  alert: {
    icon: AlertTriangle,
    color: "text-orange-400",
    bg: "bg-orange-500/15 border-orange-500/20",
    lineColor: "border-orange-500/20",
  },
  enrichment: {
    icon: Search,
    color: "text-purple-400",
    bg: "bg-purple-500/15 border-purple-500/20",
    lineColor: "border-purple-500/20",
  },
  analysis: {
    icon: Brain,
    color: "text-blue-400",
    bg: "bg-blue-500/15 border-blue-500/20",
    lineColor: "border-blue-500/20",
  },
  action: {
    icon: Wrench,
    color: "text-yellow-400",
    bg: "bg-yellow-500/15 border-yellow-500/20",
    lineColor: "border-yellow-500/20",
  },
  resolution: {
    icon: CheckCircle2,
    color: "text-green-400",
    bg: "bg-green-500/15 border-green-500/20",
    lineColor: "border-green-500/20",
  },
}

export function IncidentTimeline({ incident }: { incident: Incident }) {
  const events = incident.timeline

  if (!events.length) {
    return (
      <div className="py-8 text-center">
        <p className="text-sm text-zinc-500">No timeline events yet.</p>
      </div>
    )
  }

  return (
    <div className="relative">
      <div className="space-y-0">
        {events.map((event, i) => {
          const config = typeConfig[event.type]
          const Icon = config.icon
          const isLast = i === events.length - 1

          return (
            <div key={event.id} className="flex gap-4">
              {/* Timeline dot + line */}
              <div className="flex flex-col items-center">
                <div
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-full border shrink-0 z-10",
                    config.bg
                  )}
                >
                  <Icon className={cn("h-3.5 w-3.5", config.color)} />
                </div>
                {!isLast && (
                  <div className="w-px flex-1 border-l border-dashed border-zinc-800 my-1" />
                )}
              </div>

              {/* Content */}
              <div className={cn("flex-1 pb-6", isLast && "pb-0")}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-semibold text-zinc-200">{event.actor}</span>
                  <span className="text-[10px] text-zinc-600">
                    {formatRelativeTime(event.timestamp)}
                  </span>
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed">{event.message}</p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
