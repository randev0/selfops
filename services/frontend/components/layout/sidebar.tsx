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
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useSidebar } from "./sidebar-context"

const navItems = [
  { href: "/overview",      label: "Overview",      icon: LayoutDashboard },
  { href: "/incidents",     label: "Incidents",      icon: AlertTriangle    },
  { href: "/workloads",     label: "Workloads",      icon: Server           },
  { href: "/remediations",  label: "Remediations",   icon: Wrench           },
  { href: "/audit",         label: "Audit",          icon: ClipboardList    },
  { href: "/settings",      label: "Settings",       icon: Settings         },
]

export function Sidebar() {
  const pathname = usePathname()
  const { isOpen, isCollapsed, toggleCollapsed } = useSidebar()

  return (
    <aside
      className={cn(
        // Layout
        "fixed left-0 top-0 h-full bg-zinc-950 border-r border-zinc-800 flex flex-col z-40 overflow-hidden",
        // Smooth width + slide transitions
        "transition-[width,transform] duration-200 ease-in-out",
        // Mobile: hidden off-left by default, slides in when isOpen
        "-translate-x-full md:translate-x-0",
        isOpen && "translate-x-0",
        // Width: full on mobile (always), collapsible on desktop
        isCollapsed ? "w-14 md:w-14" : "w-64 md:w-64",
        // Mobile drawer is always full-width regardless of collapsed state
        isOpen && "w-64",
      )}
    >
      {/* Brand */}
      <div className={cn(
        "flex items-center border-b border-zinc-800 shrink-0 overflow-hidden",
        isCollapsed ? "justify-center px-0 py-4 h-14" : "gap-2.5 px-4 py-4 h-14",
      )}>
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/20 border border-blue-500/30 shrink-0">
          <Zap className="h-4 w-4 text-blue-400" />
        </div>
        <span className={cn(
          "font-semibold text-zinc-50 tracking-tight whitespace-nowrap transition-[opacity,width] duration-200 overflow-hidden",
          isCollapsed ? "opacity-0 w-0" : "opacity-100 w-auto",
        )}>
          SelfOps
        </span>
        <span className={cn(
          "ml-auto text-[10px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded px-1.5 py-0.5 whitespace-nowrap transition-[opacity,width] duration-200 overflow-hidden",
          isCollapsed ? "opacity-0 w-0 px-0 border-0" : "opacity-100",
        )}>
          v1.0
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto overflow-x-hidden">
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
              title={isCollapsed ? item.label : undefined}
              className={cn(
                "flex items-center rounded-lg text-sm font-medium transition-all duration-100 overflow-hidden",
                isCollapsed ? "justify-center px-2 py-2 gap-0" : "gap-3 px-3 py-2",
                isActive
                  ? "bg-blue-500/10 text-blue-400"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/70",
              )}
            >
              <Icon
                className={cn("h-4 w-4 shrink-0", isActive ? "text-blue-400" : "text-zinc-500")}
              />
              <span className={cn(
                "whitespace-nowrap transition-[opacity,width] duration-200 overflow-hidden",
                isCollapsed ? "opacity-0 w-0" : "opacity-100 w-auto",
              )}>
                {item.label}
              </span>
              {item.href === "/incidents" && !isCollapsed && (
                <span className="ml-auto text-[10px] font-semibold bg-orange-500/20 text-orange-400 rounded-full px-1.5 py-0.5 shrink-0">
                  5
                </span>
              )}
              {item.href === "/incidents" && isCollapsed && (
                <span className="absolute top-1 right-1 h-1.5 w-1.5 rounded-full bg-orange-400" />
              )}
            </Link>
          )
        })}
      </nav>

      {/* Cluster health */}
      <div className={cn(
        "border-t border-zinc-800 shrink-0 overflow-hidden",
        isCollapsed ? "px-2 py-3 flex justify-center" : "px-4 py-3",
      )}>
        {isCollapsed ? (
          <div className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75 animate-ping" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <div className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75 animate-ping" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
              </div>
              <span className="text-xs text-zinc-400 font-medium">Production</span>
              <span className="ml-auto text-xs text-zinc-600">k3s</span>
            </div>
            <p className="text-[10px] text-zinc-600 mt-1.5 font-mono">1 node · 2 namespaces</p>
          </>
        )}
      </div>

      {/* Collapse toggle — desktop only */}
      <button
        onClick={toggleCollapsed}
        className={cn(
          "hidden md:flex items-center border-t border-zinc-800 text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors shrink-0",
          isCollapsed ? "justify-center px-2 py-2.5" : "gap-2 px-4 py-2.5",
        )}
        aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {isCollapsed ? (
          <ChevronsRight className="h-4 w-4" />
        ) : (
          <>
            <ChevronsLeft className="h-4 w-4" />
            <span className="text-xs font-medium whitespace-nowrap">Collapse</span>
          </>
        )}
      </button>
    </aside>
  )
}
