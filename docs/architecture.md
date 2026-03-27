# SelfOps Architecture

## Overview

SelfOps is an AI-powered self-healing infrastructure platform that continuously monitors a Kubernetes cluster, detects failures, enriches incidents with contextual data, runs LLM-powered root cause analysis, and enables safe automated or operator-triggered remediation — all with a full audit trail.

---

## Component Map

```
                        ┌─────────────────────────────────┐
                        │        Kubernetes Cluster         │
                        │              (k3s)                │
                        └─────────────────────────────────┘
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           │                            │                            │
    ┌──────▼──────┐            ┌────────▼────────┐         ┌────────▼────────┐
    │  Monitoring  │            │    Platform NS   │         │   Demo App NS   │
    │  Namespace   │            │                  │         │                 │
    │              │            │  ┌─────────────┐ │         │ selfops-demo-app│
    │  Prometheus  │──alerts──► │  │ selfops-api  │ │         │ (crash/cpu/mem) │
    │  Alertmanager│            │  └──────┬──────┘ │         └────────────────┘
    │  Grafana     │            │         │         │
    │  Loki        │◄──logs─────│  ┌──────▼──────┐ │
    │  Promtail    │            │  │    worker    │ │
    └──────────────┘            │  └──────┬──────┘ │
                                │         │         │
                                │  ┌──────▼──────┐ │
                                │  │  analysis   │ │
                                │  │  service    │─┼──► OpenRouter API
                                │  └──────┬──────┘ │       (Claude Haiku)
                                │         │         │
                                │  ┌──────▼──────┐ │
                                │  │ remediation  │ │
                                │  │   runner    │─┼──► kubectl / Ansible
                                │  └─────────────┘ │
                                │                   │
                                │  ┌─────────────┐  │
                                │  │  PostgreSQL  │  │
                                │  │   Redis      │  │
                                │  └─────────────┘  │
                                │                   │
                                │  ┌─────────────┐  │
                                │  │  Next.js    │  │
                                │  │  Frontend   │  │
                                └──└─────────────┘──┘
                                          │
                                   Operator Browser
                                          │
                                   Telegram Bot
                                  (notifications)
```

---

## Components

### Monitoring Stack (namespace: `monitoring`)

#### Prometheus
- **Role:** Time-series metrics collection for all cluster components and workloads
- **Deployment:** Helm chart (`kube-prometheus-stack`)
- **Key config:** 7-day retention, 10Gi storage, scrapes all pods with `prometheus.io/scrape: "true"` annotation
- **Connects to:** Alertmanager (fires alerts), Platform API (indirectly via Alertmanager webhooks)

#### Alertmanager
- **Role:** Routes alerts from Prometheus to receivers. Configured to send webhooks to the Platform API.
- **Key config:** Groups alerts by `alertname` + `namespace`, sends to `selfops-api` webhook endpoint
- **Connects to:** Platform API (`/api/alerts/webhook`)

#### Grafana
- **Role:** Visualization dashboard for metrics and logs
- **Deployment:** Bundled with `kube-prometheus-stack`
- **Connects to:** Prometheus (metrics datasource), Loki (logs datasource)

#### Loki
- **Role:** Log aggregation backend. Stores and indexes log streams from all pods.
- **Deployment:** Helm chart (`loki-stack`) with Promtail sidecar
- **Connects to:** Grafana (visualization), Platform Worker (log queries)

#### Promtail
- **Role:** Log collector agent running as DaemonSet. Reads pod logs and ships them to Loki.
- **Connects to:** Loki

### Platform Stack (namespace: `platform`)

#### selfops-api (FastAPI)
- **Role:** Central HTTP API. Entry point for Alertmanager webhooks, operator UI requests, and action triggers.
- **Key responsibilities:**
  - Ingest alerts from Alertmanager and create/update incidents
  - Serve incident CRUD to the frontend
  - Validate and dispatch remediation action requests
  - Provide audit log endpoints
- **Tech:** Python 3.11, FastAPI, SQLAlchemy (async), asyncpg
- **Connects to:** PostgreSQL (persistence), Redis (job queue), Worker (via ARQ)

#### worker (ARQ Worker)
- **Role:** Background job processor. Runs enrichment, analysis, and notification jobs asynchronously.
- **Key jobs:**
  - `enrich_incident`: queries Prometheus and Loki for context
  - `analyze_incident`: calls the analysis service
  - `notify_incident`: sends Telegram messages
- **Tech:** Python 3.11, ARQ (async Redis job queue)
- **Connects to:** PostgreSQL, Redis, Prometheus, Loki, Analysis Service, Telegram Bot API

#### analysis-service (FastAPI)
- **Role:** Isolated LLM analysis microservice. Builds prompts, calls OpenRouter, parses responses.
- **Key responsibilities:**
  - Accepts structured incident context
  - Builds a detailed SRE prompt
  - Calls OpenRouter (Claude Haiku) with retry logic
  - Returns structured JSON analysis
- **Tech:** Python 3.11, FastAPI, httpx, tenacity
- **Connects to:** OpenRouter API (external)

#### remediation-runner (ARQ Worker)
- **Role:** Executes approved remediation actions via Ansible playbooks. Runs with cluster admin access.
- **Key responsibilities:**
  - Validates actions against policy
  - Runs Ansible playbooks via subprocess
  - Updates action status and audit logs
  - Sends completion notifications
- **Tech:** Python 3.11, ARQ, Ansible, kubectl
- **Connects to:** PostgreSQL, Redis, Kubernetes API (via kubectl), Telegram

#### PostgreSQL
- **Role:** Primary relational database. Stores all incidents, evidence, analysis results, actions, and audit logs.
- **Deployment:** Bitnami Helm chart, single primary node with 5Gi PVC
- **Connects to:** API, Worker, Remediation Runner

#### Redis
- **Role:** ARQ job queue backend and caching layer.
- **Deployment:** Bitnami Helm chart, single master with 2Gi PVC
- **Connects to:** API (enqueue jobs), Worker (process jobs), Remediation Runner (process jobs)

#### selfops-frontend (Next.js)
- **Role:** Operator dashboard. Displays incidents, evidence, analysis, and allows triggering actions.
- **Key pages:**
  - `/incidents` — paginated list of all incidents with status/severity badges
  - `/incidents/[id]` — detail view with tabs: Overview, Evidence, Analysis, Actions, Audit
- **Tech:** Next.js 14, TypeScript, Tailwind CSS, shadcn/ui
- **Connects to:** Platform API (HTTP)

### Demo App (namespace: `platform`)

#### selfops-demo-app
- **Role:** Intentionally breakable Python HTTP server for demonstrating the platform.
- **Endpoints:** `/health`, `/crash`, `/stress-cpu`, `/leak-memory`
- **Connects to:** Nothing (it is the monitored workload)

---

## Data Flow — Alert to Resolution

```
1. Demo app crashes (/crash endpoint)
2. Pod enters CrashLoopBackOff
3. Prometheus detects: kube_pod_container_status_restarts_total increases
4. Alertmanager fires PodCrashLooping alert → POST /api/alerts/webhook
5. API creates incident record, queues enrich_incident job
6. Worker runs enrich_incident:
   - Queries Prometheus for pod restart metrics
   - Queries Loki for recent pod logs
   - Stores as incident_evidence rows
7. Worker queues analyze_incident job
8. Worker calls analysis-service with enriched context
9. Analysis service builds SRE prompt, calls Claude Haiku via OpenRouter
10. Analysis result stored (summary, probable cause, recommended action)
11. Incident status → ACTION_REQUIRED
12. Worker sends Telegram notification with analysis summary
13. Operator views incident in frontend dashboard
14. Operator clicks "Restart Deployment" on Actions tab
15. API validates action against policy, creates remediation_action record
16. Remediation runner executes Ansible playbook (kubectl rollout restart)
17. Action status updated (SUCCESS or FAILED)
18. Audit log entry written
19. Telegram notification sent: action completed
20. Incident status → MONITORING → RESOLVED
```

---

## External Integrations

| Integration | Purpose | Auth |
|-------------|---------|------|
| OpenRouter API | LLM inference (Claude Haiku) | API Key (K8s secret) |
| Telegram Bot API | Operator notifications | Bot token (K8s secret) |
| Hetzner Cloud API | Infrastructure provisioning (Terraform) | API token (K8s secret) |

---

## Infrastructure

- **VPS:** Hetzner CPX32 (4 vCPU, 8GB RAM, 160GB SSD)
- **OS:** Ubuntu 24.04 LTS
- **Kubernetes:** k3s (lightweight single-node)
- **Container Runtime:** containerd (bundled with k3s)
- **Ingress:** Traefik (bundled with k3s)
- **IaC:** Terraform (Hetzner provider) + Ansible (bootstrap + k3s install + remediation)
