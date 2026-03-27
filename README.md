# SelfOps — AI-Powered Self-Healing Infrastructure

> An autonomous infrastructure platform that detects failures, enriches incidents with metrics and logs, uses an LLM to produce root cause analysis, and enables safe one-click remediation — all with a full audit trail.

**Live demo:** http://app.89.167.95.204.nip.io

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Orchestration | k3s (Kubernetes) | Lightweight single-node Kubernetes, production-grade |
| Alert ingestion | Alertmanager webhook | Native Prometheus integration |
| Metrics | Prometheus + kube-prometheus-stack | Industry standard, rich ecosystem |
| Logs | Loki + Promtail | Lightweight log aggregation, Grafana native |
| Dashboards | Grafana | Best-in-class observability UI |
| Backend API | FastAPI (Python) | Async, typed, auto-docs, fast to develop |
| Job queue | ARQ (Redis-backed) | Async Python job queue, simple and reliable |
| Database | PostgreSQL | Full ACID for audit trail and incident history |
| Cache/Queue | Redis | Fast, used by ARQ worker |
| AI analysis | OpenRouter → Claude 3 Haiku | Cost-effective LLM with structured JSON output |
| Remediation | Ansible playbooks | Idempotent, auditable, kubectl-based |
| Frontend | Next.js + Tailwind CSS | Fast SPA, live-refreshing incident list |
| Notifications | Telegram Bot API | Instant mobile alerts |
| Infrastructure | Hetzner VPS + Terraform | Reproducible cloud provisioning |

---

## Architecture

```
Kubernetes Cluster
  │
  ├── Prometheus ──── scrapes metrics ──► Alertmanager
  │                                            │
  │                                    POST /api/alerts/webhook
  │                                            │
  ├── FastAPI (selfops-api) ◄──────────────────┘
  │      │  creates incident row
  │      │  enqueues enrich_incident job
  │      │
  ├── ARQ Worker (selfops-worker)
  │      │
  │      ├── enrich_incident
  │      │     ├── query Prometheus metrics
  │      │     └── query Loki logs
  │      │
  │      ├── analyze_incident
  │      │     └── POST /analyze → Analysis Service → OpenRouter LLM
  │      │
  │      ├── notify_incident → Telegram Bot
  │      │
  │      └── run_remediation
  │            └── ansible-playbook (kubectl rollout restart / scale)
  │
  ├── Analysis Service (selfops-analysis)
  │      └── FastAPI, builds prompt, calls OpenRouter, returns structured JSON
  │
  └── Next.js Frontend (selfops-frontend)
         └── Incidents list, detail view, evidence, analysis, actions, audit log
```

---

## Demo Scenarios

### Scenario 1 — Pod Crash Loop (most dramatic)

1. Visit http://app.89.167.95.204.nip.io/incidents
2. Trigger a crash:
   ```bash
   ./scripts/trigger-demo-crash.sh
   ```
3. Within 60–90 seconds an incident appears in the dashboard
4. Watch it progress: `OPEN → ENRICHING → ANALYZING → ACTION_REQUIRED`
5. Click the incident → Analysis tab to see the LLM root cause analysis
6. Click Actions tab → Run "Restart Deployment"
7. The Ansible playbook runs, pods restart, Telegram notification arrives

### Scenario 2 — CPU Spike

```bash
./scripts/trigger-demo-cpu.sh
# Alert fires in ~2 minutes
```

### Scenario 3 — Manual webhook (instant)

```bash
curl -X POST http://app.89.167.95.204.nip.io/api/alerts/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "receiver": "selfops-webhook",
    "status": "firing",
    "alerts": [{
      "status": "firing",
      "labels": {"alertname": "PodCrashLooping", "namespace": "platform", "severity": "critical", "service": "selfops-demo-app"},
      "annotations": {"summary": "Pod is crash looping", "description": "Demo crash loop"},
      "startsAt": "2024-01-01T00:00:00Z",
      "fingerprint": "demo-manual-001"
    }],
    "groupLabels": {}, "commonLabels": {}, "commonAnnotations": {}, "externalURL": ""
  }'
```

---

## How to Run Locally

### Prerequisites

- Ubuntu 22.04+ or macOS
- Docker
- k3s or kind for local Kubernetes
- Node.js 20+

### Local development with port-forwarding

```bash
# Clone the repo
git clone https://github.com/YOUR_USER/ai-self-healing-platform.git
cd ai-self-healing-platform

# Copy and fill in secrets
cp .env.example .env
# Edit .env with your credentials

# Start port-forwarding to the cluster
export KUBECONFIG=~/.kube/config
./scripts/port-forward.sh

# API docs:    http://localhost:8000/api/docs
# Frontend:    http://localhost:3000
# Grafana:     http://localhost:3001  (admin / selfops-grafana-2024)
# Prometheus:  http://localhost:9090
# Alertmanager: http://localhost:9093
```

---

## How to Deploy

See `docs/architecture.md` for the full deployment guide. The short version:

1. Provision a Hetzner CPX32 (or equivalent) running Ubuntu 24.04
2. Install k3s: `curl -sfL https://get.k3s.io | sh -`
3. Fill in `.env` with your API keys
4. Run the phases in `CLAUDE.md` — each phase is idempotent

---

## API Reference

Full OpenAPI docs: http://app.89.167.95.204.nip.io/api/docs

Key endpoints:
- `POST /api/alerts/webhook` — Alertmanager webhook receiver
- `GET /api/incidents/` — List all incidents
- `GET /api/incidents/{id}` — Incident detail with evidence, analysis, actions, audit
- `POST /api/incidents/{id}/actions/{action_id}/run` — Trigger remediation
- `GET /api/health` — Health check
