export interface TimelineEvent {
  id: string
  timestamp: string
  type: "alert" | "enrichment" | "analysis" | "action" | "resolution"
  actor: string
  message: string
}

export interface Incident {
  id: string
  title: string
  severity: "critical" | "high" | "medium" | "low"
  status:
    | "open"
    | "enriching"
    | "analyzing"
    | "action_required"
    | "remediating"
    | "monitoring"
    | "resolved"
    | "failed_remediation"
  service: string
  namespace: string
  environment: "production" | "staging"
  createdAt: string
  lastSeen: string
  summary: string
  probableCause: string
  confidence: number
  recommendedAction: string | null
  evidencePoints: string[]
  timeline: TimelineEvent[]
  aiRecommendedActionId: string | null
}

export interface Workload {
  id: string
  name: string
  namespace: string
  type: "Deployment" | "StatefulSet" | "DaemonSet"
  status: "healthy" | "degraded" | "critical" | "unknown"
  cpu: number
  memory: number
  restarts: number
  replicas: number
  readyReplicas: number
  node: string
  lastAlert: string | null
  incidentId: string | null
}

export interface Remediation {
  id: string
  incidentId: string
  actionName: string
  service: string
  status: "success" | "failed" | "running"
  triggeredBy: string
  triggeredAt: string
  duration: string
}

export interface TimeSeriesPoint {
  time: string
  incidents: number
}

export interface ResourcePoint {
  time: string
  cpu: number
  memory: number
}

export interface ServiceRisk {
  name: string
  namespace: string
  riskLevel: "critical" | "high" | "medium"
  activeIncidents: number
  lastIncidentAt: string
}

// --- Mock Incidents ---

export const mockIncidents: Incident[] = [
  {
    id: "inc-001",
    title: "payment-worker CrashLoopBackOff — OOMKilled repeatedly",
    severity: "critical",
    status: "action_required",
    service: "payment-worker",
    namespace: "platform",
    environment: "production",
    createdAt: new Date(Date.now() - 1000 * 60 * 14).toISOString(),
    lastSeen: new Date(Date.now() - 1000 * 60 * 2).toISOString(),
    summary:
      "The payment-worker deployment has been OOMKilled 14 times in the last 20 minutes, causing a CrashLoopBackOff state. The pod is exhausting its 256Mi memory limit during peak transaction processing.",
    probableCause:
      "Memory leak in the transaction batching loop — unbounded queue accumulation under high load causing heap exhaustion.",
    confidence: 0.87,
    recommendedAction: "Restart Deployment",
    evidencePoints: [
      "Pod restarted 14 times in 20 minutes (rate: 0.7/min)",
      "Memory usage reached 256Mi limit (100% utilization) before each OOM kill",
      "Container exit code 137 (SIGKILL / OOMKilled) confirmed in all restarts",
      "Loki logs show unbounded in-memory queue growth starting at 02:41 UTC",
    ],
    timeline: [
      {
        id: "t1",
        timestamp: new Date(Date.now() - 1000 * 60 * 14).toISOString(),
        type: "alert",
        actor: "Alertmanager",
        message: "PodCrashLooping alert fired for payment-worker",
      },
      {
        id: "t2",
        timestamp: new Date(Date.now() - 1000 * 60 * 13).toISOString(),
        type: "enrichment",
        actor: "system",
        message: "Collected 5 minutes of Prometheus metrics and 120 log lines from Loki",
      },
      {
        id: "t3",
        timestamp: new Date(Date.now() - 1000 * 60 * 11).toISOString(),
        type: "analysis",
        actor: "claude-3-haiku",
        message: "AI analysis complete — 87% confidence, OOM leak identified",
      },
    ],
    aiRecommendedActionId: "restart_deployment",
  },
  {
    id: "inc-002",
    title: "auth-service high CPU — sustained 94% for 8 minutes",
    severity: "high",
    status: "analyzing",
    service: "auth-service",
    namespace: "platform",
    environment: "production",
    createdAt: new Date(Date.now() - 1000 * 60 * 22).toISOString(),
    lastSeen: new Date(Date.now() - 1000 * 60 * 1).toISOString(),
    summary:
      "The auth-service container is consuming 94% of its CPU limit for over 8 minutes. JWT validation throughput has dropped and latency p99 has spiked to 2.1s.",
    probableCause:
      "Likely bcrypt work factor misconfiguration causing excessive CPU burn on password hashing during a surge of login attempts.",
    confidence: 0.74,
    recommendedAction: "Scale Up Replicas",
    evidencePoints: [
      "CPU usage at 94% for sustained 8 minutes (limit: 500m)",
      "auth-service p99 latency increased from 120ms to 2,100ms",
      "Login request rate 3x normal (possible bot activity or retry storm)",
      "No memory pressure observed — CPU-bound issue only",
    ],
    timeline: [
      {
        id: "t1",
        timestamp: new Date(Date.now() - 1000 * 60 * 22).toISOString(),
        type: "alert",
        actor: "Alertmanager",
        message: "HighCPUUsage alert fired for auth-service",
      },
      {
        id: "t2",
        timestamp: new Date(Date.now() - 1000 * 60 * 20).toISOString(),
        type: "enrichment",
        actor: "system",
        message: "Metrics and logs collected from Prometheus and Loki",
      },
    ],
    aiRecommendedActionId: "scale_up",
  },
  {
    id: "inc-003",
    title: "metrics-gateway pod evicted — node memory pressure",
    severity: "critical",
    status: "remediating",
    service: "metrics-gateway",
    namespace: "platform",
    environment: "production",
    createdAt: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
    lastSeen: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
    summary:
      "metrics-gateway pod was evicted due to node memory pressure on node-2. The node is at 91% memory utilization. Pod is pending rescheduling.",
    probableCause:
      "Node node-2 memory saturation from multiple co-located workloads without proper resource budgeting. Node-level OOM pressure triggered pod eviction.",
    confidence: 0.92,
    recommendedAction: "Restart Deployment",
    evidencePoints: [
      "Pod eviction reason: NodeMemoryPressure on node-2",
      "Node memory at 91% (7.4 GiB / 8 GiB)",
      "3 other pods on node-2 also showing elevated memory",
      "metrics-gateway pod in Pending state, no available node",
    ],
    timeline: [
      {
        id: "t1",
        timestamp: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
        type: "alert",
        actor: "Alertmanager",
        message: "HighMemoryUsage alert fired — pod eviction detected",
      },
      {
        id: "t2",
        timestamp: new Date(Date.now() - 1000 * 60 * 43).toISOString(),
        type: "enrichment",
        actor: "system",
        message: "Collected node metrics and pod event history",
      },
      {
        id: "t3",
        timestamp: new Date(Date.now() - 1000 * 60 * 41).toISOString(),
        type: "analysis",
        actor: "claude-3-haiku",
        message: "AI analysis complete — node memory pressure identified",
      },
      {
        id: "t4",
        timestamp: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
        type: "action",
        actor: "operator",
        message: "Rollout restart triggered for metrics-gateway",
      },
    ],
    aiRecommendedActionId: "rollout_restart",
  },
  {
    id: "inc-004",
    title: "demo-api readiness probe failing — 5xx responses",
    severity: "high",
    status: "monitoring",
    service: "demo-api",
    namespace: "platform",
    environment: "production",
    createdAt: new Date(Date.now() - 1000 * 60 * 90).toISOString(),
    lastSeen: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
    summary:
      "demo-api readiness probes began failing at 03:12 UTC, causing the pod to be removed from service endpoints. Downstream consumers are receiving 503 errors.",
    probableCause:
      "Database connection pool exhaustion preventing the health check endpoint from completing successfully within the probe timeout.",
    confidence: 0.81,
    recommendedAction: "Rollout Restart",
    evidencePoints: [
      "Readiness probe /health returning 503 (timeout after 2s)",
      "PostgreSQL connection pool at 100% (50/50 connections in use)",
      "Pod removed from service endpoints — traffic routed to remaining replica",
      "Application logs show 'connection pool exhausted' errors",
    ],
    timeline: [
      {
        id: "t1",
        timestamp: new Date(Date.now() - 1000 * 60 * 90).toISOString(),
        type: "alert",
        actor: "Alertmanager",
        message: "PodCrashLooping alert — readiness probe failures",
      },
      {
        id: "t2",
        timestamp: new Date(Date.now() - 1000 * 60 * 88).toISOString(),
        type: "enrichment",
        actor: "system",
        message: "Evidence collected from Prometheus, Loki, and k8s events",
      },
      {
        id: "t3",
        timestamp: new Date(Date.now() - 1000 * 60 * 85).toISOString(),
        type: "analysis",
        actor: "claude-3-haiku",
        message: "Analysis complete — DB connection pool exhaustion identified",
      },
      {
        id: "t4",
        timestamp: new Date(Date.now() - 1000 * 60 * 20).toISOString(),
        type: "action",
        actor: "operator",
        message: "Rollout restart completed successfully",
      },
      {
        id: "t5",
        timestamp: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
        type: "resolution",
        actor: "system",
        message: "Readiness probes passing — pod back in service",
      },
    ],
    aiRecommendedActionId: "rollout_restart",
  },
  {
    id: "inc-005",
    title: "platform-backend image pull failure — ErrImagePull",
    severity: "critical",
    status: "open",
    service: "platform-backend",
    namespace: "platform",
    environment: "production",
    createdAt: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
    lastSeen: new Date(Date.now() - 1000 * 60 * 1).toISOString(),
    summary:
      "platform-backend pod is stuck in ErrImagePull state after a failed deployment. The new image tag v2.4.1 cannot be pulled from the container registry.",
    probableCause:
      "Container image v2.4.1 was pushed with an incorrect manifest or was deleted from the registry before the rollout completed.",
    confidence: 0.95,
    recommendedAction: "Rollout Restart",
    evidencePoints: [
      "Pod status: ErrImagePull for image platform-backend:v2.4.1",
      "Registry returns 404 for the image digest",
      "Previous version v2.4.0 is still available in registry",
      "Deployment rollout history shows v2.4.1 was applied 6 minutes ago",
    ],
    timeline: [
      {
        id: "t1",
        timestamp: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
        type: "alert",
        actor: "Alertmanager",
        message: "PodCrashLooping alert fired — ErrImagePull detected",
      },
    ],
    aiRecommendedActionId: null,
  },
  {
    id: "inc-006",
    title: "cache-proxy redis connection refused — all keys unavailable",
    severity: "medium",
    status: "enriching",
    service: "cache-proxy",
    namespace: "platform",
    environment: "production",
    createdAt: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
    lastSeen: new Date(Date.now() - 1000 * 60 * 3).toISOString(),
    summary:
      "cache-proxy is unable to connect to Redis and falling back to uncached requests. Cache hit rate dropped from 94% to 0%. No data loss but performance is degraded.",
    probableCause:
      "Redis pod restarted due to a configuration reload and the DNS record has not propagated to all cache-proxy instances.",
    confidence: 0.68,
    recommendedAction: null,
    evidencePoints: [
      "Redis connection errors: 'connection refused' on port 6379",
      "Cache hit rate dropped from 94% to 0%",
      "Redis pod shows 1 recent restart 9 minutes ago",
      "cache-proxy logs: ECONNREFUSED 10.96.0.45:6379",
    ],
    timeline: [
      {
        id: "t1",
        timestamp: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
        type: "alert",
        actor: "Alertmanager",
        message: "HighCPUUsage alert — fallback to uncached requests",
      },
      {
        id: "t2",
        timestamp: new Date(Date.now() - 1000 * 60 * 7).toISOString(),
        type: "enrichment",
        actor: "system",
        message: "Collecting metrics and logs from Prometheus and Loki",
      },
    ],
    aiRecommendedActionId: null,
  },
  {
    id: "inc-007",
    title: "notification-service deployment rolled back — health check timeout",
    severity: "low",
    status: "resolved",
    service: "notification-service",
    namespace: "platform",
    environment: "staging",
    createdAt: new Date(Date.now() - 1000 * 60 * 180).toISOString(),
    lastSeen: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
    summary:
      "A new deployment of notification-service in staging failed health checks during rollout and was automatically rolled back by Kubernetes. No production impact.",
    probableCause:
      "New version introduced a startup dependency on an external SMTP server that was not available in the staging environment.",
    confidence: 0.89,
    recommendedAction: null,
    evidencePoints: [
      "Deployment rollout failed: 0/2 pods ready after 120s",
      "Health check /health returning 500 during startup",
      "Application logs: 'SMTP connection failed — smtp.staging.internal:587'",
      "Kubernetes auto-rollback to previous revision triggered",
    ],
    timeline: [
      {
        id: "t1",
        timestamp: new Date(Date.now() - 1000 * 60 * 180).toISOString(),
        type: "alert",
        actor: "Alertmanager",
        message: "PodCrashLooping alert for notification-service in staging",
      },
      {
        id: "t2",
        timestamp: new Date(Date.now() - 1000 * 60 * 175).toISOString(),
        type: "enrichment",
        actor: "system",
        message: "Evidence collected",
      },
      {
        id: "t3",
        timestamp: new Date(Date.now() - 1000 * 60 * 172).toISOString(),
        type: "analysis",
        actor: "claude-3-haiku",
        message: "Analysis complete — SMTP dependency issue identified",
      },
      {
        id: "t4",
        timestamp: new Date(Date.now() - 1000 * 60 * 130).toISOString(),
        type: "resolution",
        actor: "Kubernetes",
        message: "Automatic rollback completed — service restored",
      },
    ],
    aiRecommendedActionId: null,
  },
  {
    id: "inc-008",
    title: "payment-worker failed remediation — ansible playbook error",
    severity: "high",
    status: "failed_remediation",
    service: "payment-worker",
    namespace: "platform",
    environment: "production",
    createdAt: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
    lastSeen: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    summary:
      "An attempt to restart the payment-worker deployment via Ansible playbook failed due to insufficient RBAC permissions. Manual intervention is required.",
    probableCause:
      "The remediation-runner service account lacks the 'patch' permission on deployments in the platform namespace.",
    confidence: 0.97,
    recommendedAction: "Restart Deployment",
    evidencePoints: [
      "Ansible playbook exited with code 1",
      "kubectl error: 'deployments.apps is forbidden: User cannot patch resource'",
      "RBAC audit log confirms missing ClusterRole binding",
      "Manual kubectl from node succeeds — confirms it's a permissions issue",
    ],
    timeline: [
      {
        id: "t1",
        timestamp: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
        type: "alert",
        actor: "Alertmanager",
        message: "PodCrashLooping alert for payment-worker",
      },
      {
        id: "t2",
        timestamp: new Date(Date.now() - 1000 * 60 * 58).toISOString(),
        type: "analysis",
        actor: "claude-3-haiku",
        message: "Analysis complete — restart recommended",
      },
      {
        id: "t3",
        timestamp: new Date(Date.now() - 1000 * 60 * 35).toISOString(),
        type: "action",
        actor: "operator",
        message: "Restart deployment action triggered",
      },
      {
        id: "t4",
        timestamp: new Date(Date.now() - 1000 * 60 * 32).toISOString(),
        type: "action",
        actor: "system",
        message: "Remediation FAILED — RBAC permissions denied",
      },
    ],
    aiRecommendedActionId: "restart_deployment",
  },
]

// --- Mock Workloads ---

export const mockWorkloads: Workload[] = [
  {
    id: "wl-001",
    name: "demo-api",
    namespace: "platform",
    type: "Deployment",
    status: "healthy",
    cpu: 23,
    memory: 41,
    restarts: 0,
    replicas: 2,
    readyReplicas: 2,
    node: "node-1",
    lastAlert: null,
    incidentId: null,
  },
  {
    id: "wl-002",
    name: "payment-worker",
    namespace: "platform",
    type: "Deployment",
    status: "critical",
    cpu: 12,
    memory: 98,
    restarts: 14,
    replicas: 2,
    readyReplicas: 0,
    node: "node-2",
    lastAlert: new Date(Date.now() - 1000 * 60 * 2).toISOString(),
    incidentId: "inc-001",
  },
  {
    id: "wl-003",
    name: "auth-service",
    namespace: "platform",
    type: "Deployment",
    status: "degraded",
    cpu: 94,
    memory: 55,
    restarts: 1,
    replicas: 3,
    readyReplicas: 2,
    node: "node-1",
    lastAlert: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
    incidentId: "inc-002",
  },
  {
    id: "wl-004",
    name: "metrics-gateway",
    namespace: "platform",
    type: "Deployment",
    status: "critical",
    cpu: 0,
    memory: 0,
    restarts: 2,
    replicas: 1,
    readyReplicas: 0,
    node: "node-2",
    lastAlert: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
    incidentId: "inc-003",
  },
  {
    id: "wl-005",
    name: "platform-backend",
    namespace: "platform",
    type: "Deployment",
    status: "critical",
    cpu: 0,
    memory: 0,
    restarts: 3,
    replicas: 2,
    readyReplicas: 0,
    node: "node-1",
    lastAlert: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
    incidentId: "inc-005",
  },
  {
    id: "wl-006",
    name: "cache-proxy",
    namespace: "platform",
    type: "Deployment",
    status: "degraded",
    cpu: 67,
    memory: 43,
    restarts: 0,
    replicas: 2,
    readyReplicas: 2,
    node: "node-2",
    lastAlert: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
    incidentId: "inc-006",
  },
  {
    id: "wl-007",
    name: "notification-service",
    namespace: "platform",
    type: "Deployment",
    status: "healthy",
    cpu: 8,
    memory: 22,
    restarts: 0,
    replicas: 2,
    readyReplicas: 2,
    node: "node-1",
    lastAlert: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
    incidentId: null,
  },
  {
    id: "wl-008",
    name: "selfops-api",
    namespace: "platform",
    type: "Deployment",
    status: "healthy",
    cpu: 15,
    memory: 38,
    restarts: 0,
    replicas: 2,
    readyReplicas: 2,
    node: "node-1",
    lastAlert: null,
    incidentId: null,
  },
  {
    id: "wl-009",
    name: "selfops-worker",
    namespace: "platform",
    type: "Deployment",
    status: "healthy",
    cpu: 5,
    memory: 29,
    restarts: 0,
    replicas: 1,
    readyReplicas: 1,
    node: "node-2",
    lastAlert: null,
    incidentId: null,
  },
  {
    id: "wl-010",
    name: "postgres",
    namespace: "platform",
    type: "StatefulSet",
    status: "healthy",
    cpu: 34,
    memory: 61,
    restarts: 0,
    replicas: 1,
    readyReplicas: 1,
    node: "node-1",
    lastAlert: null,
    incidentId: null,
  },
  {
    id: "wl-011",
    name: "prometheus",
    namespace: "monitoring",
    type: "StatefulSet",
    status: "healthy",
    cpu: 28,
    memory: 72,
    restarts: 0,
    replicas: 1,
    readyReplicas: 1,
    node: "node-2",
    lastAlert: null,
    incidentId: null,
  },
  {
    id: "wl-012",
    name: "node-exporter",
    namespace: "monitoring",
    type: "DaemonSet",
    status: "healthy",
    cpu: 2,
    memory: 12,
    restarts: 0,
    replicas: 2,
    readyReplicas: 2,
    node: "all",
    lastAlert: null,
    incidentId: null,
  },
]

// --- Mock Remediations ---

export const mockRemediations: Remediation[] = [
  {
    id: "rem-001",
    incidentId: "inc-004",
    actionName: "Rollout Restart",
    service: "demo-api",
    status: "success",
    triggeredBy: "operator",
    triggeredAt: new Date(Date.now() - 1000 * 60 * 20).toISOString(),
    duration: "42s",
  },
  {
    id: "rem-002",
    incidentId: "inc-003",
    actionName: "Rollout Restart",
    service: "metrics-gateway",
    status: "running",
    triggeredBy: "operator",
    triggeredAt: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
    duration: "—",
  },
  {
    id: "rem-003",
    incidentId: "inc-008",
    actionName: "Restart Deployment",
    service: "payment-worker",
    status: "failed",
    triggeredBy: "operator",
    triggeredAt: new Date(Date.now() - 1000 * 60 * 32).toISOString(),
    duration: "3s",
  },
  {
    id: "rem-004",
    incidentId: "inc-007",
    actionName: "Rollback Deployment",
    service: "notification-service",
    status: "success",
    triggeredBy: "Kubernetes",
    triggeredAt: new Date(Date.now() - 1000 * 60 * 130).toISOString(),
    duration: "28s",
  },
]

// --- Time Series Data ---

function hoursAgo(h: number): string {
  return new Date(Date.now() - h * 60 * 60 * 1000).toISOString()
}

export const mockIncidentTrend: TimeSeriesPoint[] = Array.from({ length: 24 }, (_, i) => ({
  time: hoursAgo(23 - i),
  incidents: Math.max(
    0,
    Math.round(
      4 +
        Math.sin(i * 0.7) * 2 +
        (i > 20 ? 3 : 0) +
        Math.random() * 1.5
    )
  ),
}))

export const mockCPUTrend: ResourcePoint[] = Array.from({ length: 24 }, (_, i) => ({
  time: hoursAgo(23 - i),
  cpu: Math.min(
    100,
    Math.max(
      5,
      Math.round(
        30 +
          Math.sin(i * 0.5) * 12 +
          (i > 20 ? 40 : 0) +
          Math.random() * 8
      )
    )
  ),
  memory: Math.min(
    100,
    Math.max(
      20,
      Math.round(
        55 +
          Math.sin(i * 0.3) * 10 +
          (i > 18 ? 15 : 0) +
          Math.random() * 5
      )
    )
  ),
}))

export const mockMemoryTrend: ResourcePoint[] = mockCPUTrend

// --- Services at Risk ---

export const mockServicesAtRisk: ServiceRisk[] = [
  {
    name: "payment-worker",
    namespace: "platform",
    riskLevel: "critical",
    activeIncidents: 2,
    lastIncidentAt: new Date(Date.now() - 1000 * 60 * 2).toISOString(),
  },
  {
    name: "auth-service",
    namespace: "platform",
    riskLevel: "high",
    activeIncidents: 1,
    lastIncidentAt: new Date(Date.now() - 1000 * 60 * 22).toISOString(),
  },
  {
    name: "metrics-gateway",
    namespace: "platform",
    riskLevel: "critical",
    activeIncidents: 1,
    lastIncidentAt: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
  },
  {
    name: "platform-backend",
    namespace: "platform",
    riskLevel: "high",
    activeIncidents: 1,
    lastIncidentAt: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
  },
  {
    name: "cache-proxy",
    namespace: "platform",
    riskLevel: "medium",
    activeIncidents: 1,
    lastIncidentAt: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
  },
]
