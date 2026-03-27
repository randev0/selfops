"use client"

import { useState } from "react"
import { Bell, Search, ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"

interface HeaderProps {
  title: string
  subtitle?: string
}

export function Header({ title, subtitle }: HeaderProps) {
  const [env, setEnv] = useState<"production" | "staging">("production")
  const [showEnvDropdown, setShowEnvDropdown] = useState(false)

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-4 bg-zinc-950/80 backdrop-blur-sm border-b border-zinc-800 px-6">
      {/* Page title */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-semibold text-zinc-100 truncate">{title}</h1>
          {subtitle && (
            <>
              <span className="text-zinc-700">/</span>
              <span className="text-sm text-zinc-500 truncate">{subtitle}</span>
            </>
          )}
        </div>
      </div>

      {/* Search */}
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
            "flex items-center gap-1.5 h-8 px-3 rounded-lg border text-xs font-medium transition-colors",
            env === "production"
              ? "bg-green-500/10 border-green-500/20 text-green-400"
              : "bg-yellow-500/10 border-yellow-500/20 text-yellow-400"
          )}
        >
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              env === "production" ? "bg-green-400" : "bg-yellow-400"
            )}
          />
          {env === "production" ? "Production" : "Staging"}
          <ChevronDown className="h-3 w-3 opacity-60" />
        </button>

        {showEnvDropdown && (
          <div className="absolute right-0 top-10 w-36 bg-zinc-900 border border-zinc-800 rounded-lg shadow-xl z-50 py-1 animate-fade-in">
            {(["production", "staging"] as const).map((e) => (
              <button
                key={e}
                onClick={() => {
                  setEnv(e)
                  setShowEnvDropdown(false)
                }}
                className={cn(
                  "w-full flex items-center gap-2 px-3 py-2 text-xs font-medium hover:bg-zinc-800 transition-colors",
                  env === e ? "text-zinc-100" : "text-zinc-400"
                )}
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    e === "production" ? "bg-green-400" : "bg-yellow-400"
                  )}
                />
                {e === "production" ? "Production" : "Staging"}
                {env === e && <span className="ml-auto text-blue-400">✓</span>}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Notifications */}
      <button className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors">
        <Bell className="h-4 w-4" />
        <span className="absolute -top-0.5 -right-0.5 h-4 w-4 flex items-center justify-center rounded-full bg-orange-500 text-[9px] font-bold text-white">
          5
        </span>
      </button>

      {/* User avatar */}
      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-700 border border-zinc-600 text-xs font-semibold text-zinc-300 cursor-pointer hover:bg-zinc-600 transition-colors select-none">
        OP
      </div>
    </header>
  )
}
