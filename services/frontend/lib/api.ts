const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Incident {
  id: string;
  title: string;
  status: string;
  severity: string;
  service_name: string | null;
  namespace: string | null;
  first_seen_at: string;
  last_seen_at: string;
  created_at: string;
}

export interface Evidence {
  id: string;
  evidence_type: string;
  content: Record<string, unknown>;
  captured_at: string;
}

export interface InvestigationStep {
  type: "thought" | "action" | "observation" | "conclusion" | "sop_context" | "error";
  content?: string;
  tool?: string;
  input?: string;
}

export interface Analysis {
  id: string;
  model_name: string;
  summary: string | null;
  probable_cause: string | null;
  recommendation: string | null;
  recommended_action_id: string | null;
  confidence_score: number | null;
  escalate: boolean | null;
  investigation_log: InvestigationStep[] | null;
  created_at: string;
}

export interface RemediationAction {
  id: string;
  action_type: string;
  action_name: string;
  status: string;
  requested_by: string;
  started_at: string | null;
  completed_at: string | null;
  result_summary: string | null;
  remediation_strategy: string | null;
  pr_url: string | null;
  pr_number: number | null;
  pr_branch: string | null;
  patch_file_path: string | null;
  created_at: string;
}

export interface AuditLog {
  id: string;
  actor_type: string;
  actor_id: string;
  event_type: string;
  message: string;
  created_at: string;
}

export interface IncidentDetail extends Incident {
  alert_events: Record<string, unknown>[];
  evidence: Evidence[];
  analysis_results: Analysis[];
  remediation_actions: RemediationAction[];
  audit_logs: AuditLog[];
}

export async function listIncidents(limit = 50, offset = 0): Promise<Incident[]> {
  const res = await fetch(`${API_URL}/api/incidents?limit=${limit}&offset=${offset}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Failed to fetch incidents: ${res.status}`);
  return res.json();
}

export async function getIncident(id: string): Promise<IncidentDetail> {
  const res = await fetch(`${API_URL}/api/incidents/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch incident: ${res.status}`);
  return res.json();
}

export async function runAction(
  incidentId: string,
  actionId: string,
  parameters: Record<string, unknown>
): Promise<{ action_id: string; status: string }> {
  const res = await fetch(
    `${API_URL}/api/incidents/${incidentId}/actions/${actionId}/run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ parameters }),
    }
  );
  if (!res.ok) throw new Error(`Failed to run action: ${res.status}`);
  return res.json();
}

export async function updateIncident(
  id: string,
  data: { status?: string; severity?: string }
): Promise<Incident> {
  const res = await fetch(`${API_URL}/api/incidents/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to update incident: ${res.status}`);
  return res.json();
}
