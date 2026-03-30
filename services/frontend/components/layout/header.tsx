"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import Link from "next/link"
import { Bell, Search, ChevronDown, Menu, AlertTriangle, CheckCircle2, Clock, Zap, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { useSidebar } from "./sidebar-context"
import { listIncidents, type Incident } from "@/lib/api"
import { formatRelativeTime } from "@/lib/utils"

interface HeaderProps {
  title: string
  subtitle?: string
}

// --------------------------------------------------------------------------
// Severity dot colour
// --------------------------------------------------------------------------
function severityDot(severity: string) {
  switch (severity?.toLowerCase()) {
    case "critical": return "bg-red-500"
    case "high":     return "bg-orange-500"
    case "medium":   return "bg-yellow-500"
    case "low":      return "bg-blue-400"
    default:         return "bg-zinc-500"
  }
}

// Status icon shown inside the notification row
function StatusIcon({ status }: { status: string }) {
  const s = status?.toLowerCase()
  if (["resolved", "closed"].includes(s))
    return <CheckCircle2 className="h-3.5 w-3.5 text-green-400 shrink-0" />
  if (["remediating", "action_required"].includes(s))
    return <Zap className="h-3.5 w-3.5 text-orange-400 shrink-0" />
  if (["analyzing", "enriching"].includes(s))
    return <Clock className="h-3.5 w-3.5 text-blue-400 shrink-0" />
  return <AlertTriangle className="h-3.5 w-3.5 text-yellow-400 shrink-0" />
}

const ACTIVE_STATUSES = new Set([
  "open", "enriching", "analyzing", "action_required",
  "remediating", "monitoring", "failed_remediation",
])

// --------------------------------------------------------------------------
// Notification panel
// --------------------------------------------------------------------------
function NotificationPanel({
  incidents,
  loading,
  onClose,
}: {
  incidents: Incident[]
  loading: boolean
  onClose: () => void
}) {
  const active = incidents.filter((i) => ACTIVE_STATUSES.has(i.status?.toLowerCase()))
  const recent = incidents.slice(0, 6)

  return (
    <div className="absolute right-0 top-11 w-80 bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl z-50 flex flex-col animate-fade-in overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <Bell className="h-3.5 w-3.5 text-zinc-400" />
          <span className="text-xs font-semibold text-zinc-200">Notifications</span>
          {active.length > 0 && (
            <span className="text-[10px] font-semibold bg-orange-500/20 text-orange-400 rounded-full px-1.5 py-0.5">
              {active.length} active
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="h-5 w-5 flex items-center justify-center rounded text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
          aria-label="Close notifications"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Body */}
      <div className="overflow-y-auto max-h-80">
        {loading ? (
          <div className="flex items-center justify-center py-8 gap-2">
            <div className="h-4 w-4 rounded-full border-2 border-zinc-600 border-t-blue-400 animate-spin" />
            <span className="text-xs text-zinc-500">Loading…</span>
          </div>
        ) : recent.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 gap-2 text-center px-4">
            <CheckCircle2 className="h-8 w-8 text-zinc-700" />
            <p className="text-xs font-medium text-zinc-400">All clear</p>
            <p className="text-[11px] text-zinc-600">No incidents to report</p>
          </div>
        ) : (
          <ul className="divide-y divide-zinc-800/60">
            {recent.map((incident) => (
              <li key={incident.id}>
                <Link
                  href={`/incidents/${incident.id}`}
                  onClick={onClose}
                  className="flex items-start gap-3 px-4 py-3 hover:bg-zinc-800/50 transition-colors group"
                >
                  {/* Severity dot */}
                  <div className="mt-0.5 shrink-0">
                    <span className={cn("block h-2 w-2 rounded-full mt-1", severityDot(incident.severity))} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-zinc-200 truncate group-hover:text-blue-400 transition-colors leading-snug">
                      {incident.title}
                    </p>
                    <div className="flex items-center gap-1.5 mt-1">
                      <StatusIcon status={incident.status} />
                      <span className="text-[11px] text-zinc-500 capitalize">
                        {incident.status?.replace(/_/g, " ")}
                      </span>
                      {incident.service_name && (
                        <>
                          <span className="text-zinc-700">·</span>
                          <span className="text-[11px] font-mono text-zinc-500 truncate max-w-[80px]">
                            {incident.service_name}
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Time */}
                  <span className="text-[10px] text-zinc-600 shrink-0 mt-0.5">
                    {formatRelativeTime(incident.last_seen_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2.5 border-t border-zinc-800">
        <Link
          href="/incidents"
          onClick={onClose}
          className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
        >
          View all incidents →
        </Link>
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------
// Header
// --------------------------------------------------------------------------
export function Header({ title, subtitle }: HeaderProps) {
  const [env, setEnv] = useState<"production" | "staging">("production")
  const [showEnvDropdown, setShowEnvDropdown] = useState(false)
  const [showNotifications, setShowNotifications] = useState(false)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loadingNotifs, setLoadingNotifs] = useState(false)
  const notifRef = useRef<HTMLDivElement>(null)
  const { toggle } = useSidebar()

  // Fetch incidents for badge count on mount
  useEffect(() => {
    listIncidents(20)
      .then(setIncidents)
      .catch(() => {})
  }, [])

  // Refresh when panel opens
  const openNotifications = useCallback(() => {
    setShowNotifications(true)
    setLoadingNotifs(true)
    listIncidents(20)
      .then(setIncidents)
      .catch(() => {})
      .finally(() => setLoadingNotifs(false))
  }, [])

  // Close on outside click
  useEffect(() => {
    if (!showNotifications) return
    const handler = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifications(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [showNotifications])

  // Close on Escape
  useEffect(() => {
    if (!showNotifications) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowNotifications(false)
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [showNotifications])

  const activeCount = incidents.filter((i) =>
    ACTIVE_STATUSES.has(i.status?.toLowerCase())
  ).length

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 bg-zinc-950/80 backdrop-blur-sm border-b border-zinc-800 px-4">
      {/* Hamburger — mobile only */}
      <button
        onClick={toggle}
        className="flex md:hidden h-8 w-8 items-center justify-center rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors shrink-0"
        aria-label="Open navigation"
      >
        <Menu className="h-4 w-4" />
      </button>

      {/* Page title */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h1 className="text-sm font-semibold text-zinc-100 truncate">{title}</h1>
          {subtitle && (
            <>
              <span className="text-zinc-700 hidden sm:inline">/</span>
              <span className="text-sm text-zinc-500 truncate hidden sm:inline">{subtitle}</span>
            </>
          )}
        </div>
      </div>

      {/* Search — hidden on mobile */}
      <div className="relative hidden md:flex items-center">
        <Search className="absolute left-3 h-3.5 w-3.5 text-zinc-600 pointer-events-none" />
        <input
          type="text"
          placeholder="Search..."
          className="h-8 w-48 rounded-lg bg-zinc-900 border border-zinc-800 pl-9 pr-10 text-xs text-zinc-400 placeholder-zinc-600 focus:outline-none focus:border-zinc-700 focus:ring-1 focus:ring-zinc-700 transition-colors"
        />
        <span className="absolute right-2 text-[10px] text-zinc-600 font-mono bg-zinc-800 px-1 rounded">
          ⌘K
        </span>
      </div>

      {/* Environment selector */}
      <div className="relative">
        <button
          onClick={() => setShowEnvDropdown(!showEnvDropdown)}
          className={cn(
            "flex items-center gap-1.5 h-8 px-2 sm:px-3 rounded-lg border text-xs font-medium transition-colors",
            env === "production"
              ? "bg-green-500/10 border-green-500/20 text-green-400"
              : "bg-yellow-500/10 border-yellow-500/20 text-yellow-400"
          )}
        >
          <span className={cn(
            "h-1.5 w-1.5 rounded-full shrink-0",
            env === "production" ? "bg-green-400" : "bg-yellow-400"
          )} />
          <span className="hidden sm:inline">
            {env === "production" ? "Production" : "Staging"}
          </span>
          <ChevronDown className="h-3 w-3 opacity-60 hidden sm:block" />
        </button>

        {showEnvDropdown && (
          <div className="absolute right-0 top-10 w-36 bg-zinc-900 border border-zinc-800 rounded-lg shadow-xl z-50 py-1 animate-fade-in">
            {(["production", "staging"] as const).map((e) => (
              <button
                key={e}
                onClick={() => { setEnv(e); setShowEnvDropdown(false) }}
                className={cn(
                  "w-full flex items-center gap-2 px-3 py-2 text-xs font-medium hover:bg-zinc-800 transition-colors",
                  env === e ? "text-zinc-100" : "text-zinc-400"
                )}
              >
                <span className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  e === "production" ? "bg-green-400" : "bg-yellow-400"
                )} />
                {e === "production" ? "Production" : "Staging"}
                {env === e && <span className="ml-auto text-blue-400">✓</span>}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Notifications */}
      <div ref={notifRef} className="relative shrink-0">
        <button
          onClick={showNotifications ? () => setShowNotifications(false) : openNotifications}
          className={cn(
            "relative flex h-8 w-8 items-center justify-center rounded-lg border transition-colors",
            showNotifications
              ? "bg-zinc-800 border-zinc-700 text-zinc-200"
              : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
          )}
          aria-label="Notifications"
          aria-expanded={showNotifications}
        >
          <Bell className="h-4 w-4" />
          {activeCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 h-4 w-4 flex items-center justify-center rounded-full bg-orange-500 text-[9px] font-bold text-white">
              {activeCount > 9 ? "9+" : activeCount}
            </span>
          )}
        </button>

        {showNotifications && (
          <NotificationPanel
            incidents={incidents}
            loading={loadingNotifs}
            onClose={() => setShowNotifications(false)}
          />
        )}
      </div>

      {/* User avatar */}
      <div className="hidden sm:flex h-8 w-8 items-center justify-center rounded-full bg-zinc-700 border border-zinc-600 text-xs font-semibold text-zinc-300 cursor-pointer hover:bg-zinc-600 transition-colors select-none shrink-0">
        OP
      </div>
    </header>
  )
}
