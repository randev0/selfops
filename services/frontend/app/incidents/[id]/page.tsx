"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getIncident, runAction, type IncidentDetail } from "@/lib/api";

const ALLOWED_ACTIONS = [
  {
    id: "restart_deployment",
    name: "Restart Deployment",
    description: "Rollout restart of the deployment",
    params: { deployment_name: "selfops-demo-app", namespace: "platform" },
  },
  {
    id: "rollout_restart",
    name: "Rollout Restart",
    description: "Graceful rolling restart",
    params: { deployment_name: "selfops-demo-app", namespace: "platform" },
  },
  {
    id: "scale_up",
    name: "Scale Up",
    description: "Increase replicas by 1 (max 4)",
    params: {
      deployment_name: "selfops-demo-app",
      namespace: "platform",
      max_replicas: "4",
    },
  },
];

type Tab = "overview" | "evidence" | "analysis" | "actions" | "audit";

export default function IncidentDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  const load = () =>
    getIncident(id)
      .then(setIncident)
      .catch(console.error)
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, [id]);

  const handleRunAction = async (actionId: string, params: Record<string, unknown>) => {
    try {
      setActionFeedback("Running...");
      await runAction(id, actionId, params);
      setActionFeedback("Action dispatched successfully.");
      setTimeout(() => setActionFeedback(null), 4000);
      load();
    } catch (e: unknown) {
      setActionFeedback(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  if (loading) return <div className="p-8 text-gray-500">Loading...</div>;
  if (!incident) return <div className="p-8 text-red-600">Incident not found.</div>;

  const tabs: { key: Tab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "evidence", label: `Evidence (${incident.evidence?.length ?? 0})` },
    { key: "analysis", label: `Analysis (${incident.analysis?.length ?? 0})` },
    { key: "actions", label: `Actions (${incident.actions?.length ?? 0})` },
    { key: "audit", label: `Audit (${incident.audit_logs?.length ?? 0})` },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-4">
        <div className="flex items-center gap-3">
          <Link href="/incidents" className="text-blue-600 hover:underline text-sm">
            ← Incidents
          </Link>
          <span className="text-gray-400">/</span>
          <h1 className="font-semibold text-gray-900 truncate">{incident.title}</h1>
          <span className="ml-auto text-xs bg-gray-100 px-2 py-1 rounded font-mono text-gray-500">
            {incident.status}
          </span>
          <span className="text-xs bg-red-100 text-red-800 px-2 py-1 rounded font-semibold">
            {incident.severity}
          </span>
        </div>
      </header>

      <div className="border-b bg-white px-6">
        <nav className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === t.key
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      <main className="p-6 max-w-5xl">
        {activeTab === "overview" && (
          <div className="bg-white rounded-lg shadow p-6 grid grid-cols-2 gap-4 text-sm">
            {[
              ["ID", incident.id],
              ["Status", incident.status],
              ["Severity", incident.severity],
              ["Service", incident.service_name ?? "—"],
              ["Namespace", incident.namespace ?? "—"],
              ["First Seen", new Date(incident.first_seen_at).toLocaleString()],
              ["Last Seen", new Date(incident.last_seen_at).toLocaleString()],
              ["Created", new Date(incident.created_at).toLocaleString()],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="font-medium text-gray-500">{label}</dt>
                <dd className="mt-1 text-gray-900 font-mono text-xs break-all">{value}</dd>
              </div>
            ))}
          </div>
        )}

        {activeTab === "evidence" && (
          <div className="space-y-3">
            {incident.evidence?.length === 0 && (
              <p className="text-gray-500">No evidence collected yet.</p>
            )}
            {incident.evidence?.map((ev) => (
              <div key={ev.id} className="bg-white rounded-lg shadow p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-semibold bg-blue-100 text-blue-800 px-2 py-1 rounded uppercase">
                    {ev.evidence_type}
                  </span>
                  <span className="text-xs text-gray-500">
                    {new Date(ev.captured_at).toLocaleString()}
                  </span>
                </div>
                <pre className="text-xs bg-gray-50 p-3 rounded overflow-auto max-h-48 text-gray-700">
                  {JSON.stringify(ev.content, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        )}

        {activeTab === "analysis" && (
          <div className="space-y-3">
            {incident.analysis?.length === 0 && (
              <p className="text-gray-500">No analysis available yet.</p>
            )}
            {incident.analysis?.map((a) => (
              <div key={a.id} className="bg-white rounded-lg shadow p-6 space-y-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 font-mono">{a.model_name}</span>
                  {a.confidence_score != null && (
                    <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">
                      {Math.round(a.confidence_score * 100)}% confidence
                    </span>
                  )}
                  {a.escalate && (
                    <span className="text-xs bg-red-100 text-red-800 px-2 py-1 rounded font-semibold">
                      ESCALATE
                    </span>
                  )}
                </div>
                {a.summary && (
                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Summary</p>
                    <p className="text-sm text-gray-800">{a.summary}</p>
                  </div>
                )}
                {a.probable_cause && (
                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Probable Cause</p>
                    <p className="text-sm text-gray-800">{a.probable_cause}</p>
                  </div>
                )}
                {a.recommendation && (
                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Recommendation</p>
                    <p className="text-sm text-gray-800">{a.recommendation}</p>
                  </div>
                )}
                {a.recommended_action_id && (
                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Recommended Action</p>
                    <code className="text-xs bg-gray-100 px-2 py-1 rounded">{a.recommended_action_id}</code>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {activeTab === "actions" && (
          <div className="space-y-4">
            {actionFeedback && (
              <div className="bg-blue-50 border border-blue-200 text-blue-800 px-4 py-3 rounded text-sm">
                {actionFeedback}
              </div>
            )}
            <div className="bg-white rounded-lg shadow p-4">
              <h3 className="font-semibold text-gray-900 mb-3">Available Actions</h3>
              <div className="space-y-2">
                {ALLOWED_ACTIONS.map((action) => (
                  <div
                    key={action.id}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded"
                  >
                    <div>
                      <p className="text-sm font-medium text-gray-900">{action.name}</p>
                      <p className="text-xs text-gray-500">{action.description}</p>
                    </div>
                    <button
                      onClick={() => handleRunAction(action.id, action.params)}
                      className="text-xs bg-blue-600 text-white px-3 py-2 rounded hover:bg-blue-700 transition-colors"
                    >
                      Run
                    </button>
                  </div>
                ))}
              </div>
            </div>
            {incident.actions?.length > 0 && (
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="font-semibold text-gray-900 mb-3">Action History</h3>
                <div className="space-y-2">
                  {incident.actions.map((a) => (
                    <div key={a.id} className="p-3 border rounded text-sm">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium">{a.action_name}</span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full ${
                            a.status === "SUCCESS"
                              ? "bg-green-100 text-green-800"
                              : a.status === "FAILED"
                              ? "bg-red-100 text-red-800"
                              : a.status === "RUNNING"
                              ? "bg-yellow-100 text-yellow-800"
                              : "bg-gray-100 text-gray-700"
                          }`}
                        >
                          {a.status}
                        </span>
                      </div>
                      {a.result_summary && (
                        <pre className="text-xs text-gray-600 mt-1 whitespace-pre-wrap">
                          {a.result_summary}
                        </pre>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === "audit" && (
          <div className="bg-white rounded-lg shadow p-4">
            {incident.audit_logs?.length === 0 && (
              <p className="text-gray-500 text-sm">No audit entries yet.</p>
            )}
            <div className="space-y-2">
              {incident.audit_logs?.map((log) => (
                <div key={log.id} className="flex gap-4 p-3 border-b last:border-0 text-sm">
                  <div className="text-xs text-gray-400 whitespace-nowrap pt-0.5">
                    {new Date(log.created_at).toLocaleString()}
                  </div>
                  <div>
                    <span className="font-medium text-gray-700">{log.event_type}</span>
                    <span className="text-gray-400 mx-2">·</span>
                    <span className="text-gray-600">{log.message}</span>
                    <span className="text-gray-400 text-xs ml-2">by {log.actor_id}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
