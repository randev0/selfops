import { cn } from "@/lib/utils"

interface StatusBadgeProps {
  status: string
  className?: string
}

const statusConfig: Record<
  string,
  { label: string; className: string; animated?: boolean }
> = {
  open: {
    label: "Open",
    className: "bg-zinc-500/15 text-zinc-400",
  },
  enriching: {
    label: "Enriching",
    className: "bg-purple-500/15 text-purple-400",
    animated: true,
  },
  analyzing: {
    label: "Analyzing",
    className: "bg-blue-500/15 text-blue-400",
    animated: true,
  },
  action_required: {
    label: "Action Required",
    className: "bg-orange-500/15 text-orange-400",
  },
  remediating: {
    label: "Remediating",
    className: "bg-yellow-500/15 text-yellow-400",
    animated: true,
  },
  monitoring: {
    label: "Monitoring",
    className: "bg-cyan-500/15 text-cyan-400",
  },
  resolved: {
    label: "Resolved",
    className: "bg-green-500/15 text-green-400",
  },
  failed_remediation: {
    label: "Failed",
    className: "bg-red-500/15 text-red-500",
  },
}

const dotColors: Record<string, string> = {
  enriching: "bg-purple-400",
  analyzing: "bg-blue-400",
  remediating: "bg-yellow-400",
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const key = status.toLowerCase()
  const config = statusConfig[key] ?? {
    label: status,
    className: "bg-zinc-500/15 text-zinc-400",
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium",
        config.className,
        className
      )}
    >
      {config.animated && (
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full animate-pulse-dot shrink-0",
            dotColors[key] ?? "bg-current"
          )}
        />
      )}
      {config.label}
    </span>
  )
}
