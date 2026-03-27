import { Wrench } from "lucide-react"
import { Header } from "@/components/layout/header"

export default function RemediationsPage() {
  return (
    <div className="flex flex-col min-h-full">
      <Header title="Remediations" />
      <div className="flex-1 flex flex-col items-center justify-center gap-5 p-6">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-zinc-900 border border-zinc-800">
          <Wrench className="h-8 w-8 text-zinc-600" />
        </div>
        <div className="text-center max-w-sm">
          <h2 className="text-lg font-semibold text-zinc-100">Remediation History</h2>
          <p className="text-sm text-zinc-500 mt-2">
            Full remediation history with Ansible playbook outputs, status tracking, and audit
            trails. Coming in the next release.
          </p>
        </div>
        <div className="flex flex-col gap-2 w-full max-w-sm">
          {[
            { action: "Rollout Restart", service: "demo-api", status: "success", time: "20m ago" },
            { action: "Rollout Restart", service: "metrics-gateway", status: "running", time: "8m ago" },
            { action: "Restart Deployment", service: "payment-worker", status: "failed", time: "32m ago" },
          ].map((r, i) => (
            <div
              key={i}
              className="flex items-center gap-3 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3"
            >
              <div
                className={`h-2 w-2 rounded-full shrink-0 ${
                  r.status === "success"
                    ? "bg-green-400"
                    : r.status === "failed"
                    ? "bg-red-400"
                    : "bg-yellow-400 animate-pulse"
                }`}
              />
              <span className="text-xs font-medium text-zinc-300 flex-1">{r.action}</span>
              <span className="text-xs font-mono text-zinc-500">{r.service}</span>
              <span className="text-xs text-zinc-600">{r.time}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
