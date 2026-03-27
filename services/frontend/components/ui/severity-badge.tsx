import { cn } from "@/lib/utils"

interface SeverityBadgeProps {
  severity: "critical" | "high" | "medium" | "low" | string
  className?: string
}

const severityConfig: Record<string, { label: string; className: string }> = {
  critical: {
    label: "Critical",
    className: "bg-red-500/15 text-red-400 border border-red-500/20",
  },
  high: {
    label: "High",
    className: "bg-orange-500/15 text-orange-400 border border-orange-500/20",
  },
  medium: {
    label: "Medium",
    className: "bg-yellow-500/15 text-yellow-400 border border-yellow-500/20",
  },
  low: {
    label: "Low",
    className: "bg-blue-500/15 text-blue-400 border border-blue-500/20",
  },
}

export function SeverityBadge({ severity, className }: SeverityBadgeProps) {
  const config = severityConfig[severity.toLowerCase()] ?? {
    label: severity,
    className: "bg-zinc-500/15 text-zinc-400 border border-zinc-500/20",
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium",
        config.className,
        className
      )}
    >
      {config.label}
    </span>
  )
}

export function SeverityDot({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    critical: "bg-red-400",
    high: "bg-orange-400",
    medium: "bg-yellow-400",
    low: "bg-blue-400",
  }
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 rounded-full shrink-0",
        colors[severity.toLowerCase()] ?? "bg-zinc-400"
      )}
    />
  )
}
