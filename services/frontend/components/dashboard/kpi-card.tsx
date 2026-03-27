import { type LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"
import { type ReactNode } from "react"

interface KpiCardProps {
  title: string
  value: string | number
  delta?: string
  deltaType?: "up" | "down" | "neutral"
  icon: LucideIcon
  iconColor?: string
  trend?: number[]
  className?: string
  children?: ReactNode
}

function MiniSparkline({ data }: { data: number[] }) {
  if (!data || data.length < 2) return null
  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1
  const width = 80
  const height = 28
  const step = width / (data.length - 1)

  const points = data
    .map((v, i) => {
      const x = i * step
      const y = height - ((v - min) / range) * height
      return `${x},${y}`
    })
    .join(" ")

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      className="opacity-50"
    >
      <polyline
        points={points}
        stroke="#3b82f6"
        strokeWidth="1.5"
        fill="none"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function KpiCard({
  title,
  value,
  delta,
  deltaType = "neutral",
  icon: Icon,
  iconColor = "text-blue-400",
  trend,
  className,
}: KpiCardProps) {
  const iconBg = iconColor.replace("text-", "bg-").replace("-400", "-500/10")

  const deltaColors = {
    up: "text-red-400",
    down: "text-green-400",
    neutral: "text-zinc-500",
  }

  const deltaPrefix = {
    up: "↑",
    down: "↓",
    neutral: "",
  }

  return (
    <div
      className={cn(
        "bg-zinc-900 border border-zinc-800 rounded-xl p-5 flex flex-col gap-3",
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div
          className={cn(
            "flex h-9 w-9 items-center justify-center rounded-lg",
            iconBg
          )}
        >
          <Icon className={cn("h-4 w-4", iconColor)} />
        </div>
        {trend && trend.length > 0 && <MiniSparkline data={trend} />}
      </div>

      <div>
        <p className="text-2xl font-bold text-zinc-50 tabular-nums leading-none">{value}</p>
        <p className="text-xs text-zinc-500 mt-1 font-medium">{title}</p>
      </div>

      {delta && (
        <p className={cn("text-xs font-medium", deltaColors[deltaType])}>
          {deltaPrefix[deltaType]} {delta}
        </p>
      )}
    </div>
  )
}
