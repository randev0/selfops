"use client"

import { useState } from "react"
import { Sparkles, CheckCircle2 } from "lucide-react"
import { type Incident } from "@/lib/mock-data"

interface AIAnalysisPanelProps {
  incident: Incident
}

export function AIAnalysisPanel({ incident }: AIAnalysisPanelProps) {
  const [note, setNote] = useState("")

  const confidencePct = Math.round(incident.confidence * 100)
  const confidenceColor =
    incident.confidence >= 0.7
      ? "bg-green-500"
      : incident.confidence >= 0.4
      ? "bg-yellow-500"
      : "bg-red-500"

  const confidenceTextColor =
    incident.confidence >= 0.7
      ? "text-green-400"
      : incident.confidence >= 0.4
      ? "text-yellow-400"
      : "text-red-400"

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 bg-[radial-gradient(ellipse_at_top_right,_rgba(59,130,246,0.03)_0%,_transparent_60%)]">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/10 border border-blue-500/20">
          <Sparkles className="h-3.5 w-3.5 text-blue-400" />
        </div>
        <span className="text-sm font-semibold text-zinc-100">AI Analysis</span>
        <span className="ml-auto text-[10px] font-mono bg-zinc-800 border border-zinc-700 text-zinc-400 rounded px-1.5 py-0.5">
          claude-3-haiku
        </span>
      </div>

      {/* Confidence meter */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-zinc-500">Confidence</span>
          <span className={`text-xs font-semibold ${confidenceTextColor}`}>
            {confidencePct}%
          </span>
        </div>
        <div className="h-1.5 w-full bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={`h-full ${confidenceColor} rounded-full transition-all duration-500`}
            style={{ width: `${confidencePct}%` }}
          />
        </div>
      </div>

      {/* Probable Cause */}
      <div className="mb-4">
        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">
          Probable Cause
        </p>
        <p className="text-xs text-zinc-300 leading-relaxed">{incident.probableCause}</p>
      </div>

      {/* Evidence Points */}
      {incident.evidencePoints.length > 0 && (
        <div className="mb-4">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">
            Evidence
          </p>
          <ul className="space-y-1.5">
            {incident.evidencePoints.slice(0, 4).map((point, i) => (
              <li key={i} className="flex items-start gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0 mt-0.5" />
                <span className="text-xs text-zinc-400 leading-relaxed">{point}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Operator Note */}
      <div className="mb-3">
        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">
          Operator Note
        </p>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add context for the team..."
          rows={2}
          className="w-full bg-zinc-800/50 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-zinc-600 resize-none transition-colors"
        />
      </div>

      {/* Footer */}
      <p className="text-[10px] text-zinc-600">
        Analyzed {Math.floor((Date.now() - new Date(incident.createdAt).getTime()) / 60000 + 2)}m ago ·{" "}
        <span className="font-mono">claude-3-haiku</span>
      </p>
    </div>
  )
}
