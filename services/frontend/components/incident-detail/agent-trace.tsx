"use client"

import { useState, useEffect } from "react"
import { ChevronDown, ChevronRight, Brain, Wrench, Eye, BookOpen, GitPullRequest, ExternalLink } from "lucide-react"
import { getIncident, type InvestigationStep, type RemediationAction } from "@/lib/api"
import { cn } from "@/lib/utils"

interface AgentTraceProps {
  incidentId: string
}

const stepIcon = {
  thought: Brain,
  action: Wrench,
  observation: Eye,
  conclusion: Brain,
  sop_context: BookOpen,
  error: Eye,
}

const stepColor: Record<string, string> = {
  thought: "text-blue-400 bg-blue-500/10 border-blue-500/20",
  action: "text-orange-400 bg-orange-500/10 border-orange-500/20",
  observation: "text-green-400 bg-green-500/10 border-green-500/20",
  conclusion: "text-purple-400 bg-purple-500/10 border-purple-500/20",
  sop_context: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20",
  error: "text-red-400 bg-red-500/10 border-red-500/20",
}

function StepRow({ step, index }: { step: InvestigationStep; index: number }) {
  const [open, setOpen] = useState(step.type === "sop_context" ? false : index < 3)
  const Icon = stepIcon[step.type] ?? Eye
  const color = stepColor[step.type] ?? "text-zinc-400 bg-zinc-800 border-zinc-700"

  const label = step.type === "action"
    ? `Action: ${step.tool ?? "tool"}`
    : step.type.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())

  const bodyText =
    step.type === "action"
      ? `Tool: ${step.tool}\nInput: ${step.input ?? ""}`
      : step.content ?? ""

  return (
    <div className={cn("border rounded-lg overflow-hidden", color.split(" ").slice(1).join(" "))}>
      <button
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-white/5 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <Icon className={cn("h-3.5 w-3.5 shrink-0", color.split(" ")[0])} />
        <span className={cn("text-xs font-semibold flex-1", color.split(" ")[0])}>{label}</span>
        {open ? (
          <ChevronDown className="h-3 w-3 text-zinc-600" />
        ) : (
          <ChevronRight className="h-3 w-3 text-zinc-600" />
        )}
      </button>
      {open && bodyText && (
        <pre className="px-3 pb-3 text-[11px] text-zinc-400 whitespace-pre-wrap leading-relaxed font-mono border-t border-current/10">
          {bodyText}
        </pre>
      )}
    </div>
  )
}

function PRCard({ action }: { action: RemediationAction }) {
  if (!action.pr_url) return null
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg bg-purple-500/5 border border-purple-500/20">
      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded bg-purple-500/10 border border-purple-500/20">
        <GitPullRequest className="h-3.5 w-3.5 text-purple-400" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold text-purple-300">
            GitOps PR #{action.pr_number}
          </span>
          <span className={cn(
            "text-[10px] font-medium px-1.5 py-0.5 rounded-full",
            action.status === "PENDING_MERGE"
              ? "bg-yellow-500/15 text-yellow-400"
              : action.status === "SUCCESS"
              ? "bg-green-500/15 text-green-400"
              : "bg-zinc-700 text-zinc-400"
          )}>
            {action.status}
          </span>
        </div>
        {action.pr_branch && (
          <p className="text-[10px] font-mono text-zinc-500 mt-0.5 truncate">{action.pr_branch}</p>
        )}
        {action.patch_file_path && (
          <p className="text-[10px] text-zinc-500 mt-0.5">File: {action.patch_file_path}</p>
        )}
        <a
          href={action.pr_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 mt-1.5 text-[11px] text-purple-400 hover:text-purple-300 transition-colors"
        >
          View Pull Request
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </div>
  )
}

export function AgentTrace({ incidentId }: AgentTraceProps) {
  const [data, setData] = useState<{
    steps: InvestigationStep[]
    prActions: RemediationAction[]
    summary: string | null
    probableCause: string | null
    confidence: number | null
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getIncident(incidentId)
      .then((incident) => {
        const latestAnalysis = incident.analysis_results?.[0] ?? null
        const steps = latestAnalysis?.investigation_log ?? []
        const prActions = (incident.remediation_actions ?? []).filter(
          (a) => a.remediation_strategy === "GITOPS_PR"
        )
        setData({
          steps,
          prActions,
          summary: latestAnalysis?.summary ?? null,
          probableCause: latestAnalysis?.probable_cause ?? null,
          confidence: latestAnalysis?.confidence_score ?? null,
        })
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false))
  }, [incidentId])

  if (loading) {
    return (
      <div className="space-y-2 animate-pulse">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-9 rounded-lg bg-zinc-800" />
        ))}
      </div>
    )
  }

  if (error || !data) {
    return (
      <p className="text-xs text-zinc-500 italic">
        {error ?? "No agent trace available."}
      </p>
    )
  }

  const { steps, prActions, probableCause, confidence } = data

  return (
    <div className="space-y-4">
      {/* GitOps PR cards */}
      {prActions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
            GitOps Pull Requests
          </p>
          {prActions.map((a) => (
            <PRCard key={a.id} action={a} />
          ))}
        </div>
      )}

      {/* Agent conclusion summary */}
      {probableCause && (
        <div className="p-3 rounded-lg bg-zinc-800/60 border border-zinc-700">
          <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">
            Probable Cause
          </p>
          <p className="text-xs text-zinc-300 leading-relaxed">{probableCause}</p>
          {confidence !== null && (
            <div className="mt-2 flex items-center gap-2">
              <div className="flex-1 h-1 bg-zinc-700 rounded-full overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded-full",
                    confidence >= 0.7 ? "bg-green-500" : confidence >= 0.4 ? "bg-yellow-500" : "bg-red-500"
                  )}
                  style={{ width: `${Math.round(confidence * 100)}%` }}
                />
              </div>
              <span className="text-[10px] text-zinc-500">
                {Math.round(confidence * 100)}% confidence
              </span>
            </div>
          )}
        </div>
      )}

      {/* Investigation steps */}
      {steps.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
            Investigation Steps ({steps.length})
          </p>
          <div className="space-y-1.5">
            {steps.map((step, i) => (
              <StepRow key={i} step={step} index={i} />
            ))}
          </div>
        </div>
      ) : (
        <p className="text-xs text-zinc-500 italic">
          No investigation steps recorded yet.
        </p>
      )}
    </div>
  )
}
