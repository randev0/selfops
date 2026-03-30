import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatRelativeTime(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime()
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  return `${months}mo ago`
}

export function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (minutes < 60) return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`
}

export function getSeverityColor(severity: string): string {
  switch (severity.toLowerCase()) {
    case "critical":
      return "bg-red-500/15 text-red-400 border border-red-500/20"
    case "high":
      return "bg-orange-500/15 text-orange-400 border border-orange-500/20"
    case "medium":
      return "bg-yellow-500/15 text-yellow-400 border border-yellow-500/20"
    case "low":
      return "bg-blue-500/15 text-blue-400 border border-blue-500/20"
    default:
      return "bg-zinc-500/15 text-zinc-400 border border-zinc-500/20"
  }
}

export function getStatusColor(status: string): string {
  switch (status.toLowerCase()) {
    case "open":
      return "bg-zinc-500/15 text-zinc-400"
    case "enriching":
      return "bg-purple-500/15 text-purple-400"
    case "analyzing":
      return "bg-blue-500/15 text-blue-400"
    case "action_required":
      return "bg-orange-500/15 text-orange-400"
    case "remediating":
      return "bg-yellow-500/15 text-yellow-400"
    case "monitoring":
      return "bg-cyan-500/15 text-cyan-400"
    case "resolved":
      return "bg-green-500/15 text-green-400"
    case "failed_remediation":
      return "bg-red-500/15 text-red-500"
    default:
      return "bg-zinc-500/15 text-zinc-400"
  }
}

export function formatIncidentDuration(createdAt: string): string {
  return formatDuration(Date.now() - new Date(createdAt).getTime())
}

export function formatAbsoluteTime(isoString: string): string {
  return new Date(isoString).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
}

const GRAFANA_BASE = "https://grafana-selfops.steadigital.com"

/** Grafana Explore URL — Prometheus pod restart rate for the given service. */
export function buildGrafanaUrl(service: string, namespace: string, createdAt: string): string {
  const from = new Date(createdAt).getTime() - 5 * 60 * 1000
  const to = Date.now() + 60 * 1000
  const left = JSON.stringify({
    datasource: "prometheus",
    queries: [{
      expr: `rate(kube_pod_container_status_restarts_total{namespace="${namespace}",pod=~"${service}.*"}[5m]) * 300`,
      refId: "A",
      legendFormat: "{{pod}}",
    }],
    range: { from: String(from), to: String(to) },
  })
  return `${GRAFANA_BASE}/explore?orgId=1&left=${encodeURIComponent(left)}`
}

/** Grafana Explore URL — Loki logs for the given service / namespace. */
export function buildLokiUrl(service: string, namespace: string, createdAt: string): string {
  const from = new Date(createdAt).getTime() - 5 * 60 * 1000
  const to = Date.now() + 60 * 1000
  const left = JSON.stringify({
    datasource: "loki",
    queries: [{
      expr: `{namespace="${namespace}",app="${service}"}`,
      refId: "A",
    }],
    range: { from: String(from), to: String(to) },
  })
  return `${GRAFANA_BASE}/explore?orgId=1&left=${encodeURIComponent(left)}`
}
