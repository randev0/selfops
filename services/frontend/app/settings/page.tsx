import { Settings } from "lucide-react"
import { Header } from "@/components/layout/header"

export default function SettingsPage() {
  return (
    <div className="flex flex-col min-h-full">
      <Header title="Settings" />
      <div className="flex-1 p-6">
        <div className="max-w-2xl">
          <div className="flex items-center gap-3 mb-6">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-zinc-900 border border-zinc-800">
              <Settings className="h-5 w-5 text-zinc-500" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-zinc-100">Settings</h2>
              <p className="text-sm text-zinc-500">Platform configuration and integrations</p>
            </div>
          </div>

          <div className="space-y-4">
            {[
              {
                section: "Integrations",
                items: [
                  { label: "OpenRouter API Key", value: "sk-or-****", status: "connected" },
                  { label: "Telegram Bot", value: "@selfops_bot", status: "connected" },
                  { label: "Prometheus", value: "prometheus-operated:9090", status: "connected" },
                  { label: "Loki", value: "loki:3100", status: "connected" },
                ],
              },
              {
                section: "Remediation Policy",
                items: [
                  { label: "Auto-remediation", value: "Disabled", status: "inactive" },
                  { label: "Allowed namespaces", value: "platform", status: "ok" },
                  { label: "Max auto-replicas", value: "4", status: "ok" },
                ],
              },
              {
                section: "Notifications",
                items: [
                  { label: "Telegram alerts", value: "Enabled — critical + high", status: "connected" },
                  { label: "Alert grouping", value: "10s window", status: "ok" },
                ],
              },
            ].map((section) => (
              <div key={section.section} className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
                <div className="px-5 py-3 border-b border-zinc-800">
                  <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                    {section.section}
                  </h3>
                </div>
                <div className="divide-y divide-zinc-800/50">
                  {section.items.map((item) => (
                    <div key={item.label} className="flex items-center justify-between px-5 py-3">
                      <span className="text-sm text-zinc-400">{item.label}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-mono text-zinc-300">{item.value}</span>
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${
                            item.status === "connected"
                              ? "bg-green-400"
                              : item.status === "inactive"
                              ? "bg-zinc-600"
                              : "bg-blue-400"
                          }`}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <p className="text-xs text-zinc-600 mt-6">
            Full settings configuration UI coming in the next release.
          </p>
        </div>
      </div>
    </div>
  )
}
