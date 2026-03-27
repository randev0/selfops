# SelfOps — AI-Powered Self-Healing Infrastructure

> An autonomous infrastructure platform that detects failures, enriches incidents with metrics and logs, uses an LLM to produce root cause analysis, and enables safe one-click or automated remediation — all with a full audit trail.

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Orchestration | k3s (Kubernetes) | Lightweight, production-grade, single-binary |
| API Backend | FastAPI (Python) | Async, fast, auto-generates OpenAPI docs |
| Job Queue | ARQ + Redis | Async Redis-backed jobs, perfect for background enrichment |
| Database | PostgreSQL | Reliable, rich JSONB support for flexible evidence storage |
| LLM Inference | OpenRouter (Claude Haiku) | Cheap, fast, high-quality SRE analysis |
| Metrics | Prometheus + kube-prometheus-stack | Industry standard, rich Kubernetes metrics |
| Logs | Loki + Promtail | Efficient log aggregation, integrates with Grafana |
| Visualization | Grafana | Best-in-class metrics/logs dashboards |
| Frontend | Next.js 14 + Tailwind + shadcn/ui | Fast, type-safe, great DX |
| Remediation | Ansible playbooks | Declarative, idempotent, human-readable |
| Notifications | Telegram Bot API | Simple, reliable push notifications |
| Infrastructure | Hetzner + Terraform | Cost-effective, reproducible infra |

---

## Architecture Overview

```
Alertmanager ──webhook──► selfops-api ──queue──► worker
                                │                    │
                                │              enrich (Prometheus + Loki)
                                │              analyze (OpenRouter LLM)
                                │              notify (Telegram)
                                │
                          PostgreSQL
                                │
                          Next.js Frontend ──► operator browser
                                │
                    remediation-runner ──► Ansible ──► kubectl
```

Full architecture details: [docs/architecture.md](docs/architecture.md)

---

## Demo Scenarios

### Scenario 1: Pod Crash Loop
1. Trigger: `./scripts/trigger-demo-crash.sh`
2. Watch: Pod enters CrashLoopBackOff
3. SelfOps: Detects → Enriches → Analyzes → Notifies (Telegram)
4. Operator: Views incident in dashboard, clicks "Restart Deployment"
5. SelfOps: Runs Ansible, pod recovers, sends completion notification

### Scenario 2: High CPU Usage
1. Trigger: `./scripts/trigger-demo-cpu.sh`
2. Watch: CPU alert fires after ~2 minutes
3. SelfOps: Same pipeline, recommends "Scale Up Replicas"

### Scenario 3: Memory Leak
1. Trigger: `kubectl exec -n platform <pod> -- curl localhost:8080/leak-memory`
2. Watch: HighMemoryUsage alert fires
3. SelfOps: Recommends restart

---

## Running Locally (Port Forwarding)

```bash
# Prerequisites: kubectl configured, cluster running
./scripts/port-forward.sh

# Access:
# API Docs:      http://localhost:8000/api/docs
# Frontend:      http://localhost:3000
# Grafana:       http://localhost:3001  (admin / selfops-grafana-2024)
# Prometheus:    http://localhost:9090
# Alertmanager:  http://localhost:9093
```

---

## Deploying from Scratch

### Prerequisites
- Hetzner Cloud account with API token
- Domain or use nip.io (included)
- Telegram bot token (create via @BotFather)
- OpenRouter API key (openrouter.ai)

### Steps

**1. Clone the repo:**
```bash
git clone https://github.com/your-username/ai-self-healing-platform.git
cd ai-self-healing-platform
```

**2. Fill in secrets:**
```bash
cp .env.example .env
# Edit .env with your actual values
```

**3. Provision infrastructure (optional — if not using existing VPS):**
```bash
cd infra/terraform
terraform init
terraform apply
```

**4. Bootstrap the server:**
```bash
cd infra/ansible
ansible-playbook -i inventory.ini bootstrap.yml
ansible-playbook -i inventory.ini k3s.yml
```

**5. Deploy the platform:**
```bash
# Create namespaces
kubectl apply -f k8s/base/

# Install observability stack
helm install kube-prom prometheus-community/kube-prometheus-stack \
  -n monitoring -f k8s/monitoring/prometheus-values.yaml

helm install loki grafana/loki-stack \
  -n monitoring -f k8s/monitoring/loki-values.yaml

# Install platform services
source .env
helm install postgres bitnami/postgresql -n platform \
  --set auth.postgresPassword=$POSTGRES_PASSWORD \
  --set auth.database=selfops \
  --set auth.username=selfops \
  --set auth.password=$POSTGRES_PASSWORD

helm install redis bitnami/redis -n platform \
  --set auth.enabled=false \
  --set replica.replicaCount=0

# Create secrets
kubectl create secret generic selfops-secrets -n platform \
  --from-literal=openrouter-api-key=$OPENROUTER_API_KEY \
  --from-literal=postgres-password=$POSTGRES_PASSWORD \
  --from-literal=telegram-bot-token=$TELEGRAM_BOT_TOKEN \
  --from-literal=telegram-chat-id=$TELEGRAM_CHAT_ID

# Deploy platform workloads
kubectl apply -f k8s/platform/
kubectl apply -f k8s/demo-app/
kubectl apply -f k8s/monitoring/alert-rules.yaml
```

---

## API Documentation

Full API spec: [docs/api-spec.md](docs/api-spec.md)

Live Swagger UI: `http://<server-ip>/api/docs`

---

## Data Model

Full schema documentation: [docs/data-model.md](docs/data-model.md)

---

## Project Structure

```
.
├── docs/               # Architecture, data model, API spec
├── infra/
│   ├── terraform/      # Hetzner infrastructure
│   └── ansible/        # Server bootstrap + remediation playbooks
├── k8s/
│   ├── base/           # Namespaces
│   ├── monitoring/     # Prometheus, Loki, alert rules
│   ├── platform/       # All platform service manifests
│   └── demo-app/       # Intentionally breakable demo workload
├── services/
│   ├── api/            # FastAPI backend
│   ├── worker/         # ARQ background worker
│   ├── analysis-service/ # LLM analysis microservice
│   ├── remediation-runner/ # Ansible-based remediation executor
│   └── frontend/       # Next.js operator dashboard
└── scripts/            # Demo and utility scripts
```
