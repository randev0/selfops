import { ClipboardList } from "lucide-react"
import { Header } from "@/components/layout/header"

export default function AuditPage() {
  return (
    <div className="flex flex-col min-h-full">
      <Header title="Audit" />
      <div className="flex-1 flex flex-col items-center justify-center gap-5 p-6">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-zinc-900 border border-zinc-800">
          <ClipboardList className="h-8 w-8 text-zinc-600" />
        </div>
        <div className="text-center max-w-sm">
          <h2 className="text-lg font-semibold text-zinc-100">Audit Log</h2>
          <p className="text-sm text-zinc-500 mt-2">
            Complete chronological audit trail of all system events, operator actions, and
            automated remediations with full metadata. Coming in the next release.
          </p>
        </div>
        <div className="flex flex-col gap-1 w-full max-w-md">
          {[
            { actor: "system", event: "Incident created", detail: "payment-worker OOM", time: "14m ago" },
            { actor: "claude-3-haiku", event: "Analysis completed", detail: "87% confidence", time: "11m ago" },
            { actor: "operator", event: "Action triggered", detail: "restart_deployment", time: "8m ago" },
            { actor: "system", event: "Enrichment started", detail: "auth-service CPU", time: "22m ago" },
            { actor: "Kubernetes", event: "Pod evicted", detail: "node memory pressure", time: "45m ago" },
          ].map((entry, i) => (
            <div
              key={i}
              className="flex items-center gap-3 px-4 py-3 hover:bg-zinc-900/50 rounded-xl border border-transparent hover:border-zinc-800 transition-colors"
            >
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-800 text-[9px] font-bold text-zinc-400 shrink-0">
                {entry.actor.slice(0, 2).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-xs font-semibold text-zinc-300">{entry.event}</span>
                <span className="text-xs text-zinc-600 ml-2">{entry.detail}</span>
              </div>
              <span className="text-xs text-zinc-600 shrink-0">{entry.time}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
