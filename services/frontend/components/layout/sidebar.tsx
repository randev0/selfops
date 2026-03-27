"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Zap,
  LayoutDashboard,
  AlertTriangle,
  Server,
  Wrench,
  ClipboardList,
  Settings,
} from "lucide-react"
import { cn } from "@/lib/utils"

const navItems = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard },
  { href: "/incidents", label: "Incidents", icon: AlertTriangle },
  { href: "/workloads", label: "Workloads", icon: Server },
  { href: "/remediations", label: "Remediations", icon: Wrench },
  { href: "/audit", label: "Audit", icon: ClipboardList },
  { href: "/settings", label: "Settings", icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="fixed left-0 top-0 h-full w-56 bg-zinc-950 border-r border-zinc-800 flex flex-col z-40">
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-zinc-800">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/20 border border-blue-500/30">
          <Zap className="h-4 w-4 text-blue-400" />
        </div>
        <span className="font-semibold text-zinc-50 tracking-tight">SelfOps</span>
        <span className="ml-auto text-[10px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded px-1.5 py-0.5">
          v1.0
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive =
            item.href === "/overview"
              ? pathname === "/" || pathname === "/overview"
              : pathname.startsWith(item.href)

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-100",
                isActive
                  ? "bg-blue-500/10 text-blue-400"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/70"
              )}
            >
              <Icon
                className={cn("h-4 w-4 shrink-0", isActive ? "text-blue-400" : "text-zinc-500")}
              />
              {item.label}
              {item.href === "/incidents" && (
                <span className="ml-auto text-[10px] font-semibold bg-orange-500/20 text-orange-400 rounded-full px-1.5 py-0.5">
                  5
                </span>
              )}
            </Link>
          )
        })}
      </nav>

      {/* Cluster health */}
      <div className="px-4 py-3 border-t border-zinc-800">
        <div className="flex items-center gap-2">
          <div className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75 animate-ping" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
          </div>
          <span className="text-xs text-zinc-400 font-medium">Production</span>
          <span className="ml-auto text-xs text-zinc-600">k3s</span>
        </div>
        <p className="text-[10px] text-zinc-600 mt-1.5 font-mono">1 node · 2 namespaces</p>
      </div>
    </aside>
  )
}
