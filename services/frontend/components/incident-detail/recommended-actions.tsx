"use client"

import { useState } from "react"
import { RefreshCw, RotateCcw, ArrowUp, Shield, Loader2 } from "lucide-react"
import { type Incident } from "@/lib/mock-data"
import { cn } from "@/lib/utils"

interface Action {
  id: string
  name: string
  description: string
  icon: typeof RefreshCw
}

const actions: Action[] = [
  {
    id: "restart_deployment",
    name: "Restart Deployment",
    description: "Rollout restart of deployment — replaces all pods",
    icon: RefreshCw,
  },
  {
    id: "rollout_restart",
    name: "Rollout Restart",
    description: "Graceful rolling restart — replaces pods one at a time",
    icon: RotateCcw,
  },
  {
    id: "scale_up",
    name: "Scale Replicas",
    description: "Increase replica count by 1 (max 4)",
    icon: ArrowUp,
  },
]

interface RecommendedActionsProps {
  incident: Incident
}

export function RecommendedActions({ incident }: RecommendedActionsProps) {
  const [runningAction, setRunningAction] = useState<string | null>(null)
  const [completedActions, setCompletedActions] = useState<Set<string>>(new Set())

  const handleRun = async (actionId: string) => {
    if (runningAction) return
    setRunningAction(actionId)
    await new Promise((r) => setTimeout(r, 2000))
    setRunningAction(null)
    setCompletedActions((prev) => new Set([...prev, actionId]))
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <span className="text-sm font-semibold text-zinc-100">Recommended Actions</span>
        <span className="ml-auto flex items-center gap-1 text-[10px] font-medium bg-green-500/10 text-green-400 border border-green-500/20 rounded-full px-2 py-0.5">
          <Shield className="h-2.5 w-2.5" />
          safe & bounded
        </span>
      </div>

      {/* Actions list */}
      <div className="space-y-2">
        {actions.map((action) => {
          const Icon = action.icon
          const isAiRecommended = action.id === incident.aiRecommendedActionId
          const isRunning = runningAction === action.id
          const isDone = completedActions.has(action.id)
          const isDisabled = runningAction !== null && runningAction !== action.id

          return (
            <div
              key={action.id}
              className={cn(
                "rounded-lg border p-3 transition-colors",
                isAiRecommended
                  ? "border-l-2 border-l-blue-500 border-zinc-700 bg-zinc-800/50"
                  : "border-zinc-800 bg-zinc-800/30"
              )}
            >
              {isAiRecommended && (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-blue-400 bg-blue-500/10 rounded px-1.5 py-0.5 mb-2">
                  AI Recommended
                </span>
              )}
              <div className="flex items-center gap-3">
                <div
                  className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-lg shrink-0",
                    isAiRecommended ? "bg-blue-500/15" : "bg-zinc-700/50"
                  )}
                >
                  <Icon
                    className={cn("h-3.5 w-3.5", isAiRecommended ? "text-blue-400" : "text-zinc-400")}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-zinc-200">{action.name}</p>
                  <p className="text-[11px] text-zinc-500 truncate">{action.description}</p>
                </div>
                <button
                  onClick={() => handleRun(action.id)}
                  disabled={isDisabled || isDone}
                  className={cn(
                    "flex items-center gap-1.5 shrink-0 h-7 px-3 rounded-md text-xs font-semibold transition-all",
                    isDone
                      ? "bg-green-500/10 text-green-400 border border-green-500/20 cursor-default"
                      : isRunning
                      ? "bg-blue-500/10 text-blue-400 border border-blue-500/20 cursor-wait"
                      : isAiRecommended
                      ? "bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-40"
                      : "bg-zinc-700 text-zinc-300 hover:bg-zinc-600 disabled:opacity-40"
                  )}
                >
                  {isRunning ? (
                    <>
                      <Loader2 className="h-3 w-3 animate-spin" />
                      Running
                    </>
                  ) : isDone ? (
                    "Done"
                  ) : (
                    "Run"
                  )}
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {/* Warning */}
      <p className="text-[10px] text-zinc-600 mt-3 flex items-center gap-1">
        <Shield className="h-2.5 w-2.5" />
        Actions are logged and audited
      </p>
    </div>
  )
}
