# SelfOps — Autonomous Build Instructions for Claude Code

## What You Are Building

**SelfOps** is an AI-powered self-healing infrastructure platform that:
- Watches a Kubernetes cluster with Prometheus + Loki
- Detects failures (pod crashes, high CPU, OOM) via Alertmanager
- Enriches incidents with logs and metrics automatically
- Uses an LLM (via OpenRouter) to produce root cause analysis
- Lets an operator trigger safe remediation actions (restart, scale, rollout)
- Shows everything in a Next.js dashboard with a full audit trail
- Sends Telegram notifications on key events

**Stack:** k3s · FastAPI · PostgreSQL · Redis · Next.js · Prometheus · Loki · Grafana · Ansible · Terraform · OpenRouter API

---

## Prime Directives — Never Break These

1. **Commit to git after every phase completes.** Use the message format: `feat: complete phase N - <phase name>`
2. **Never hardcode secrets.** All credentials go in Kubernetes secrets or `.env` files. `.env` is in `.gitignore`.
3. **Always add resource limits** to every Kubernetes manifest you write. Include both `requests` and `limits` for CPU and memory.
4. **If a phase fails**, stop immediately. Create a file called `BLOCKERS.md` in the repo root describing exactly what failed, what error was produced, and what you tried. Then stop and wait.
5. **Never delete existing files** unless replacing them with a better version of the same file.
6. **Work sequentially.** Do not start Phase N+1 until Phase N passes its success checklist.
7. **Always run `kubectl get pods -A`** at the end of each phase to confirm no pods are in a crash loop before declaring success.

---

## Environment — What Is Already Done

- Ubuntu 24.04 LTS VPS on Hetzner (CPX32: 4 vCPU, 8GB RAM, 160GB SSD)
- You can SSH into the server as root
- The GitHub repo `ai-self-healing-platform` exists and is cloned on this server
- This CLAUDE.md is in the repo root

---

## Required Secrets — Set These Before Starting Phase 3

Create a `.env` file in the repo root (it is gitignored). You will reference these values when creating Kubernetes secrets. The operator will fill in the actual values before you start:

```
HETZNER_API_TOKEN=
OPENROUTER_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
POSTGRES_PASSWORD=selfops_secure_pass_2024
REDIS_PASSWORD=
```

When you need to create Kubernetes secrets, always read from these env vars using:
```bash
source .env
kubectl create secret generic selfops-secrets -n platform \
  --from-literal=openrouter-api-key=$OPENROUTER_API_KEY \
  --from-literal=postgres-password=$POSTGRES_PASSWORD \
  --from-literal=telegram-bot-token=$TELEGRAM_BOT_TOKEN \
  --from-literal=telegram-chat-id=$TELEGRAM_CHAT_ID \
  --dry-run=client -o yaml | kubectl apply -f -
```

---

## Repository Structure to Create

Ensure this structure exists before Phase 2. Create any missing directories:

```
ai-self-healing-platform/
  CLAUDE.md                    ← this file
  BLOCKERS.md                  ← create only if something fails
  .env.example                 ← template with all keys, no values
  .gitignore
  README.md
  docs/
    architecture.md
    data-model.md
    api-spec.md
  infra/
    terraform/
      main.tf
      variables.tf
      outputs.tf
    ansible/
      inventory.ini
      bootstrap.yml
      k3s.yml
      remediation/
        restart_deployment.yml
        rollout_restart.yml
        scale_up.yml
  k8s/
    base/
      namespace-platform.yaml
      namespace-monitoring.yaml
    monitoring/
      prometheus-values.yaml
      loki-values.yaml
      alert-rules.yaml
    platform/
      postgres.yaml
      redis.yaml
      api-deployment.yaml
      worker-deployment.yaml
      analysis-service-deployment.yaml
      remediation-runner-deployment.yaml
      frontend-deployment.yaml
      ingress.yaml
    demo-app/
      deployment.yaml
      service.yaml
  services/
    api/
      app/
        main.py
        routers/
        models/
        schemas/
        services/
        dependencies.py
        config.py
      migrations/
        001_initial.sql
      Dockerfile
      requirements.txt
    worker/
      worker.py
      jobs/
        enrich.py
        analyze.py
        notify.py
      Dockerfile
      requirements.txt
    analysis-service/
      main.py
      prompt_builder.py
      llm_client.py
      schemas.py
      Dockerfile
      requirements.txt
    remediation-runner/
      orchestrator.py
      policy.py
      runner.py
      Dockerfile
      requirements.txt
    frontend/
      (Next.js project created by create-next-app)
  scripts/
    port-forward.sh
    trigger-demo-crash.sh
    trigger-demo-cpu.sh
```

---

## Phase 1 — Repository & Foundations

### Goal
Git repo is structured, documented, and committed.

### Tasks

**1.1 Create all directories in the structure above.**

**1.2 Create `.gitignore`:**
```
.env
*.env.*
!.env.example
node_modules/
__pycache__/
*.pyc
.terraform/
*.tfstate
*.tfstate.backup
.terraform.lock.hcl
k3s.yaml
dist/
.next/
*.egg-info/
.venv/
```

**1.3 Create `.env.example`:**
```
HETZNER_API_TOKEN=
OPENROUTER_API_KEY=
POSTGRES_PASSWORD=
REDIS_PASSWORD=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

**1.4 Create `docs/architecture.md`** — write a clear description of every component and how they connect. Use the component list from the project description above.

**1.5 Create `docs/data-model.md`** — document every database table that will be created in the migrations. See Phase 4 for the full schema.

**1.6 Create `docs/api-spec.md`** — document all API endpoints. See Phase 4 for the full list.

**1.7 Create `README.md`** with: project name (SelfOps), one-line description, tech stack table, architecture overview, how to run locally, how to deploy.

### Phase 1 Success Checklist
- [ ] All directories exist
- [ ] `.gitignore` is in place
- [ ] `.env.example` has all required keys
- [ ] `docs/` folder has all three files with real content
- [ ] `README.md` exists with meaningful content
- [ ] `git add -A && git commit -m "feat: complete phase 1 - repo foundations"` succeeds

---

## Phase 2 — Kubernetes Base Setup

### Goal
k3s is running and you can deploy workloads. Namespaces are created.

### Check if k3s is already installed
```bash
kubectl get nodes
```
If this returns a node in Ready state, k3s is already installed. Skip to task 2.3.

### Tasks

**2.1 Install k3s (if not already installed):**
```bash
curl -sfL https://get.k3s.io | sh -
# Wait for it to be ready
sleep 30
kubectl get nodes
```

**2.2 Set up kubectl access:**
```bash
mkdir -p ~/.kube
cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
chmod 600 ~/.kube/config
export KUBECONFIG=~/.kube/config
echo 'export KUBECONFIG=~/.kube/config' >> ~/.bashrc
```

**2.3 Create namespaces:**

Create `k8s/base/namespace-platform.yaml`:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: platform
  labels:
    name: platform
```

Create `k8s/base/namespace-monitoring.yaml`:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: monitoring
  labels:
    name: monitoring
```

Apply them:
```bash
kubectl apply -f k8s/base/namespace-platform.yaml
kubectl apply -f k8s/base/namespace-monitoring.yaml
kubectl get namespaces
```

**2.4 Install Helm:**
```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
```

**2.5 Add all required Helm repos:**
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
```

**2.6 Install cert-manager (needed for TLS later):**
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml
sleep 30
kubectl get pods -n cert-manager
```

### Phase 2 Success Checklist
- [ ] `kubectl get nodes` shows node in Ready state
- [ ] `kubectl get namespaces` shows `platform` and `monitoring`
- [ ] `helm version` works
- [ ] All helm repos added and updated
- [ ] `kubectl get pods -A` shows no CrashLoopBackOff pods
- [ ] `git commit -m "feat: complete phase 2 - k3s and cluster foundations"`

---

## Phase 3 — Observability Stack

### Goal
Prometheus is scraping metrics, Alertmanager is configured to send webhooks to the platform API, Loki is collecting logs, Grafana is accessible.

### Tasks

**3.1 Create Prometheus + Alertmanager + Grafana values file at `k8s/monitoring/prometheus-values.yaml`:**

```yaml
grafana:
  enabled: true
  adminPassword: "selfops-grafana-2024"
  service:
    type: ClusterIP
  persistence:
    enabled: true
    size: 2Gi
  resources:
    requests:
      memory: "256Mi"
      cpu: "100m"
    limits:
      memory: "512Mi"
      cpu: "300m"

alertmanager:
  enabled: true
  alertmanagerSpec:
    resources:
      requests:
        memory: "64Mi"
        cpu: "50m"
      limits:
        memory: "128Mi"
        cpu: "100m"
  config:
    global:
      resolve_timeout: 5m
    route:
      group_by: ['alertname', 'namespace']
      group_wait: 10s
      group_interval: 10s
      repeat_interval: 1h
      receiver: selfops-webhook
    receivers:
      - name: selfops-webhook
        webhook_configs:
          - url: "http://selfops-api.platform.svc.cluster.local:8000/api/alerts/webhook"
            send_resolved: true

prometheus:
  prometheusSpec:
    retention: 7d
    retentionSize: "8GB"
    resources:
      requests:
        memory: "512Mi"
        cpu: "200m"
      limits:
        memory: "1Gi"
        cpu: "500m"
    storageSpec:
      volumeClaimTemplate:
        spec:
          accessModes: ["ReadWriteOnce"]
          resources:
            requests:
              storage: 10Gi

prometheusOperator:
  resources:
    requests:
      memory: "128Mi"
      cpu: "100m"
    limits:
      memory: "256Mi"
      cpu: "200m"

kubeStateMetrics:
  resources:
    requests:
      memory: "64Mi"
      cpu: "50m"
    limits:
      memory: "128Mi"
      cpu: "100m"

nodeExporter:
  resources:
    requests:
      memory: "32Mi"
      cpu: "25m"
    limits:
      memory: "64Mi"
      cpu: "100m"
```

**3.2 Install kube-prometheus-stack:**
```bash
helm install kube-prom prometheus-community/kube-prometheus-stack \
  -n monitoring \
  -f k8s/monitoring/prometheus-values.yaml \
  --timeout 10m
```

Wait for all pods to be ready:
```bash
kubectl wait --for=condition=ready pod -l app.kubernetes.io/instance=kube-prom -n monitoring --timeout=300s
```

**3.3 Create Loki values at `k8s/monitoring/loki-values.yaml`:**
```yaml
loki:
  enabled: true
  persistence:
    enabled: true
    size: 10Gi
  resources:
    requests:
      memory: "256Mi"
      cpu: "100m"
    limits:
      memory: "512Mi"
      cpu: "300m"
  config:
    limits_config:
      retention_period: 168h
    table_manager:
      retention_deletes_enabled: true
      retention_period: 168h

promtail:
  enabled: true
  resources:
    requests:
      memory: "64Mi"
      cpu: "25m"
    limits:
      memory: "128Mi"
      cpu: "100m"
```

**3.4 Install Loki:**
```bash
helm install loki grafana/loki-stack \
  -n monitoring \
  -f k8s/monitoring/loki-values.yaml \
  --timeout 10m
```

**3.5 Create the demo app at `k8s/demo-app/deployment.yaml`:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: selfops-demo-app
  namespace: platform
  labels:
    app: selfops-demo-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: selfops-demo-app
  template:
    metadata:
      labels:
        app: selfops-demo-app
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
    spec:
      containers:
        - name: demo-app
          image: python:3.11-slim
          command: ["python", "-c"]
          args:
            - |
              import http.server, threading, time, os, sys
              class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                  if self.path == '/health':
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'ok')
                  elif self.path == '/crash':
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'crashing...')
                    threading.Thread(target=lambda: (time.sleep(1), os._exit(1))).start()
                  elif self.path == '/stress-cpu':
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'stressing cpu for 60s...')
                    def burn():
                      end = time.time() + 60
                      while time.time() < end:
                        x = sum(i*i for i in range(10000))
                    threading.Thread(target=burn).start()
                  elif self.path == '/leak-memory':
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'leaking memory...')
                    leak = []
                    def grow():
                      while True:
                        leak.append(' ' * 1024 * 1024)
                        time.sleep(0.5)
                    threading.Thread(target=grow, daemon=True).start()
                  else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'selfops demo app running')
                def log_message(self, fmt, *args):
                  print(f"[demo-app] {fmt % args}", flush=True)
              print("SelfOps demo app starting on :8080", flush=True)
              http.server.HTTPServer(('', 8080), Handler).serve_forever()
          ports:
            - containerPort: 8080
          resources:
            requests:
              memory: "64Mi"
              cpu: "50m"
            limits:
              memory: "256Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: selfops-demo-app
  namespace: platform
spec:
  selector:
    app: selfops-demo-app
  ports:
    - port: 8080
      targetPort: 8080
```

Apply:
```bash
kubectl apply -f k8s/demo-app/deployment.yaml
kubectl wait --for=condition=ready pod -l app=selfops-demo-app -n platform --timeout=120s
```

**3.6 Create Prometheus alert rules at `k8s/monitoring/alert-rules.yaml`:**
```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: selfops-rules
  namespace: monitoring
  labels:
    release: kube-prom
spec:
  groups:
    - name: selfops.demo-app
      interval: 30s
      rules:
        - alert: PodCrashLooping
          expr: rate(kube_pod_container_status_restarts_total{namespace="platform"}[5m]) * 60 > 0.5
          for: 1m
          labels:
            severity: critical
            service: selfops-demo-app
          annotations:
            summary: "Pod is crash looping"
            description: "Pod {{ $labels.pod }} in namespace {{ $labels.namespace }} is restarting frequently"

        - alert: HighCPUUsage
          expr: sum(rate(container_cpu_usage_seconds_total{namespace="platform", container!=""}[2m])) by (pod, container) > 0.4
          for: 2m
          labels:
            severity: warning
            service: selfops-demo-app
          annotations:
            summary: "High CPU usage detected"
            description: "Container {{ $labels.container }} in pod {{ $labels.pod }} is using high CPU"

        - alert: HighMemoryUsage
          expr: sum(container_memory_working_set_bytes{namespace="platform", container!=""}) by (pod, container) / sum(container_spec_memory_limit_bytes{namespace="platform", container!=""}) by (pod, container) > 0.8
          for: 2m
          labels:
            severity: warning
            service: selfops-demo-app
          annotations:
            summary: "High memory usage detected"
            description: "Container {{ $labels.container }} is using over 80% of its memory limit"
```

Apply:
```bash
kubectl apply -f k8s/monitoring/alert-rules.yaml
```

### Phase 3 Success Checklist
- [ ] `kubectl get pods -n monitoring` — all pods Running
- [ ] `kubectl port-forward -n monitoring svc/kube-prom-grafana 3000:80 &` — Grafana accessible
- [ ] `kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 &` — Prometheus UI accessible
- [ ] Demo app is running: `kubectl get pods -n platform`
- [ ] Alert rules appear in Prometheus UI under Alerts
- [ ] Triggering `/crash` on demo app eventually fires an alert
- [ ] `git commit -m "feat: complete phase 3 - observability stack"`

---

## Phase 4 — Platform Core

### Goal
PostgreSQL and Redis running. FastAPI backend ingesting alerts. Worker processing jobs. Frontend showing incidents. All connected.

### Tasks

**4.1 Install PostgreSQL:**
```bash
source .env
helm install postgres bitnami/postgresql -n platform \
  --set auth.postgresPassword=$POSTGRES_PASSWORD \
  --set auth.database=selfops \
  --set auth.username=selfops \
  --set auth.password=$POSTGRES_PASSWORD \
  --set primary.persistence.size=5Gi \
  --set primary.resources.requests.memory=256Mi \
  --set primary.resources.requests.cpu=100m \
  --set primary.resources.limits.memory=512Mi \
  --set primary.resources.limits.cpu=300m
```

**4.2 Install Redis:**
```bash
helm install redis bitnami/redis -n platform \
  --set auth.enabled=false \
  --set master.persistence.size=2Gi \
  --set master.resources.requests.memory=64Mi \
  --set master.resources.requests.cpu=50m \
  --set master.resources.limits.memory=128Mi \
  --set master.resources.limits.cpu=100m \
  --set replica.replicaCount=0
```

Wait for both:
```bash
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=postgresql -n platform --timeout=180s
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=redis -n platform --timeout=180s
```

**4.3 Run database migrations:**

Create `services/api/migrations/001_initial.sql` with the full schema:
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TYPE incident_status AS ENUM (
  'OPEN', 'ENRICHING', 'ANALYZING', 'ACTION_REQUIRED',
  'REMEDIATING', 'MONITORING', 'RESOLVED', 'FAILED_REMEDIATION', 'CLOSED'
);

CREATE TYPE severity_level AS ENUM ('critical', 'warning', 'info', 'unknown');

CREATE TABLE incidents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  title TEXT NOT NULL,
  status incident_status NOT NULL DEFAULT 'OPEN',
  severity severity_level NOT NULL DEFAULT 'unknown',
  service_name TEXT,
  namespace TEXT,
  environment TEXT DEFAULT 'production',
  fingerprint TEXT UNIQUE,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE alert_events (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
  alert_name TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  labels JSONB DEFAULT '{}',
  annotations JSONB DEFAULT '{}',
  starts_at TIMESTAMPTZ,
  ends_at TIMESTAMPTZ,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE incident_evidence (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
  evidence_type TEXT NOT NULL CHECK (evidence_type IN ('metric', 'log', 'alert', 'analysis_input')),
  content JSONB NOT NULL,
  captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE analysis_results (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
  model_provider TEXT NOT NULL,
  model_name TEXT NOT NULL,
  prompt_version TEXT NOT NULL DEFAULT 'v1',
  summary TEXT,
  probable_cause TEXT,
  recommendation TEXT,
  recommended_action_id TEXT,
  confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
  escalate BOOLEAN DEFAULT FALSE,
  raw_output JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TYPE action_status AS ENUM ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED');
CREATE TYPE execution_mode AS ENUM ('manual', 'auto');

CREATE TABLE remediation_actions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
  action_type TEXT NOT NULL,
  action_name TEXT NOT NULL,
  requested_by TEXT NOT NULL DEFAULT 'operator',
  execution_mode execution_mode NOT NULL DEFAULT 'manual',
  status action_status NOT NULL DEFAULT 'PENDING',
  parameters JSONB DEFAULT '{}',
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  result_summary TEXT,
  raw_output JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE audit_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
  actor_type TEXT NOT NULL CHECK (actor_type IN ('user', 'system', 'automation')),
  actor_id TEXT NOT NULL DEFAULT 'system',
  event_type TEXT NOT NULL,
  message TEXT NOT NULL,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_incidents_status ON incidents(status);
CREATE INDEX idx_incidents_created_at ON incidents(created_at DESC);
CREATE INDEX idx_incidents_fingerprint ON incidents(fingerprint);
CREATE INDEX idx_alert_events_incident_id ON alert_events(incident_id);
CREATE INDEX idx_incident_evidence_incident_id ON incident_evidence(incident_id);
CREATE INDEX idx_analysis_results_incident_id ON analysis_results(incident_id);
CREATE INDEX idx_remediation_actions_incident_id ON remediation_actions(incident_id);
CREATE INDEX idx_audit_logs_incident_id ON audit_logs(incident_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);
```

Apply the migrations:
```bash
# Port-forward postgres
kubectl port-forward -n platform svc/postgres-postgresql 5432:5432 &
PG_PF_PID=$!
sleep 5

source .env
PGPASSWORD=$POSTGRES_PASSWORD psql -h 127.0.0.1 -U selfops -d selfops -f services/api/migrations/001_initial.sql

kill $PG_PF_PID
```

**4.4 Build the FastAPI backend:**

Create `services/api/requirements.txt`:
```
fastapi==0.110.0
uvicorn[standard]==0.27.0
sqlalchemy==2.0.27
asyncpg==0.29.0
alembic==1.13.1
pydantic==2.6.1
pydantic-settings==2.2.0
redis==5.0.1
arq==0.25.0
httpx==0.27.0
python-jose==3.3.0
passlib==1.7.4
python-multipart==0.0.9
prometheus-client==0.20.0
structlog==24.1.0
```

Create `services/api/app/config.py`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://selfops:password@postgres-postgresql.platform.svc.cluster.local:5432/selfops"
    redis_url: str = "redis://redis-master.platform.svc.cluster.local:6379"
    openrouter_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    environment: str = "production"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()
```

Create `services/api/app/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import alerts, incidents, actions, audit, health
import structlog

log = structlog.get_logger()

app = FastAPI(
    title="SelfOps API",
    description="AI-powered self-healing infrastructure platform API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(incidents.router, prefix="/api/incidents", tags=["incidents"])
app.include_router(actions.router, prefix="/api/incidents", tags=["actions"])
app.include_router(audit.router, prefix="/api/incidents", tags=["audit"])

@app.on_event("startup")
async def startup():
    log.info("SelfOps API starting up")
```

Create `services/api/app/routers/health.py`:
```python
from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok", "service": "selfops-api"}
```

Create `services/api/app/routers/alerts.py` — this is the most critical endpoint. It must:
- Accept POST from Alertmanager (Alertmanager sends a list of alerts in `alerts` field)
- For each alert, compute a fingerprint from the alert's labels
- Check if an incident with that fingerprint already exists
- If yes: update `last_seen_at` and add the alert event
- If no: create a new incident and queue an enrichment job
- Return 200 always (Alertmanager retries on non-2xx)

Create `services/api/app/routers/incidents.py` with:
- `GET /api/incidents` — list all incidents, ordered by created_at DESC, with pagination (limit/offset)
- `GET /api/incidents/{id}` — full incident detail with evidence, analysis, actions, audit
- `PATCH /api/incidents/{id}` — update status or severity

Create `services/api/app/routers/actions.py` with:
- `POST /api/incidents/{id}/actions/{action_id}/run` — trigger a remediation action
- `GET /api/incidents/{id}/actions` — list all actions for an incident

Create `services/api/app/routers/audit.py` with:
- `GET /api/incidents/{id}/audit` — full audit trail for an incident

**4.5 Create the Dockerfile for the API at `services/api/Dockerfile`:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

**4.6 Build the Worker:**

Create `services/worker/requirements.txt`:
```
arq==0.25.0
httpx==0.27.0
asyncpg==0.29.0
sqlalchemy==2.0.27
redis==5.0.1
structlog==24.1.0
pydantic==2.6.1
pydantic-settings==2.2.0
```

Create `services/worker/worker.py` — an ARQ worker that defines three job functions:
- `enrich_incident(ctx, incident_id)`: query Prometheus API for recent metrics, query Loki API for recent logs, store as incident_evidence rows
- `analyze_incident(ctx, incident_id)`: gather all evidence, call the analysis service HTTP API, store result
- `notify_incident(ctx, incident_id, message)`: send a Telegram message via Bot API

Create `services/worker/Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "arq", "worker.WorkerSettings"]
```

**4.7 Build the Frontend:**
```bash
cd services/frontend
npx create-next-app@latest . --typescript --tailwind --eslint --app --no-src-dir --import-alias "@/*" --use-npm
npx shadcn-ui@latest init --defaults
npx shadcn-ui@latest add table badge button card dialog toast
cd ../..
```

Create these pages in the Next.js app:
- `app/page.tsx` — redirect to `/incidents`
- `app/incidents/page.tsx` — incidents list with columns: Status badge, Severity, Service, Namespace, First seen, Age
- `app/incidents/[id]/page.tsx` — incident detail with: header (title, status, severity), tabs (Overview, Evidence, Analysis, Actions, Audit)
  - Overview tab: incident metadata
  - Evidence tab: list of evidence items (metrics and logs)
  - Analysis tab: LLM summary, probable cause, confidence score, recommended action
  - Actions tab: available remediation actions with Run button for each
  - Audit tab: chronological audit log

Create `services/frontend/lib/api.ts` — a typed API client that wraps all fetch calls to the backend. Use `NEXT_PUBLIC_API_URL` env var for the base URL.

Create `services/frontend/Dockerfile`:
```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

**4.8 Build Docker images and push to the k3s containerd:**

For k3s, you can import images directly without a registry:
```bash
# Build each image
docker build -t selfops-api:latest services/api/
docker build -t selfops-worker:latest services/worker/
docker build -t selfops-frontend:latest services/frontend/

# Import into k3s
docker save selfops-api:latest | k3s ctr images import -
docker save selfops-worker:latest | k3s ctr images import -
docker save selfops-frontend:latest | k3s ctr images import -
```

Note: set `imagePullPolicy: Never` in all Kubernetes manifests that use these images.

**4.9 Create Kubernetes manifests for all platform services in `k8s/platform/`:**

Every manifest must include resource requests and limits. Use the selfops-secrets secret for credentials. Key env vars to inject:
- `DATABASE_URL` — built from postgres service name and credentials
- `REDIS_URL` — from redis service name
- `OPENROUTER_API_KEY` — from secret
- `TELEGRAM_BOT_TOKEN` — from secret
- `TELEGRAM_CHAT_ID` — from secret
- `PROMETHEUS_URL` — `http://prometheus-operated.monitoring.svc.cluster.local:9090`
- `LOKI_URL` — `http://loki.monitoring.svc.cluster.local:3100`
- `ANALYSIS_SERVICE_URL` — `http://selfops-analysis.platform.svc.cluster.local:8001`

Create the Kubernetes secrets:
```bash
source .env
kubectl create secret generic selfops-secrets -n platform \
  --from-literal=openrouter-api-key=$OPENROUTER_API_KEY \
  --from-literal=postgres-password=$POSTGRES_PASSWORD \
  --from-literal=telegram-bot-token=$TELEGRAM_BOT_TOKEN \
  --from-literal=telegram-chat-id=$TELEGRAM_CHAT_ID \
  --dry-run=client -o yaml | kubectl apply -f -
```

Apply all manifests:
```bash
kubectl apply -f k8s/platform/
kubectl wait --for=condition=ready pod -l app=selfops-api -n platform --timeout=120s
```

**4.10 Create the Ingress at `k8s/platform/ingress.yaml`:**

Use the server's IP with nip.io for free DNS:
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: selfops-ingress
  namespace: platform
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  rules:
    - host: "app.YOUR_SERVER_IP.nip.io"
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: selfops-api
                port:
                  number: 8000
          - path: /
            pathType: Prefix
            backend:
              service:
                name: selfops-frontend
                port:
                  number: 3000
```

Replace `YOUR_SERVER_IP` with the actual VPS IP address.

### Phase 4 Success Checklist
- [ ] PostgreSQL and Redis pods are Running
- [ ] Database schema applied successfully
- [ ] API is deployed: `curl http://YOUR_IP/api/health` returns `{"status":"ok"}`
- [ ] API docs accessible at `http://YOUR_IP/api/docs`
- [ ] Sending a test webhook to `/api/alerts/webhook` creates an incident in the database
- [ ] Worker picks up the job and attempts enrichment (check worker pod logs)
- [ ] Frontend is accessible at `http://app.YOUR_IP.nip.io/incidents`
- [ ] Incident list shows real data from the database
- [ ] `git commit -m "feat: complete phase 4 - platform core services"`

---

## Phase 5 — AI Analysis Layer

### Goal
Incidents are automatically analyzed by an LLM via OpenRouter. Analysis results are visible in the frontend.

### Tasks

**5.1 Create `services/analysis-service/requirements.txt`:**
```
fastapi==0.110.0
uvicorn==0.27.0
httpx==0.27.0
pydantic==2.6.1
pydantic-settings==2.2.0
structlog==24.1.0
tenacity==8.2.3
```

**5.2 Create `services/analysis-service/schemas.py`:**
```python
from pydantic import BaseModel
from typing import Optional, List

class AnalysisRequest(BaseModel):
    incident_id: str
    incident_title: str
    service_name: Optional[str]
    namespace: Optional[str]
    alert_name: str
    alert_labels: dict
    alert_annotations: dict
    metrics_summary: Optional[str]
    log_lines: Optional[str]
    allowed_actions: List[dict]

class AnalysisResponse(BaseModel):
    summary: str
    probable_cause: str
    evidence_points: List[str]
    recommended_action_id: Optional[str]
    confidence: float
    escalate: bool
    raw_output: dict
```

**5.3 Create `services/analysis-service/prompt_builder.py`:**

Build a function `build_prompt(request: AnalysisRequest) -> str` that produces this exact prompt structure:
```
You are an expert Site Reliability Engineer analyzing a Kubernetes infrastructure incident.
Your job is to produce a concise, accurate incident analysis based on the provided evidence.
Be factual and specific. Do not speculate beyond the evidence.

INCIDENT TITLE: {incident_title}
SERVICE: {service_name} | NAMESPACE: {namespace}
ALERT: {alert_name}
ALERT LABELS: {alert_labels_formatted}
ALERT ANNOTATIONS: {alert_annotations_formatted}

RECENT METRICS (last 5 minutes):
{metrics_summary or "No metrics available"}

RELEVANT LOG LINES:
{log_lines or "No logs available"}

AVAILABLE REMEDIATION ACTIONS:
{actions_formatted}

Respond with a JSON object containing exactly these fields:
{
  "summary": "2-3 sentence plain English description of what happened",
  "probable_cause": "The most likely root cause based on the evidence",
  "evidence_points": ["key evidence 1", "key evidence 2", "key evidence 3"],
  "recommended_action_id": "the action_id from the available actions, or null if none apply",
  "confidence": 0.0 to 1.0,
  "escalate": true if the situation needs immediate human attention, false otherwise
}
Respond only with the JSON object. No markdown, no explanation, no code blocks.
```

**5.4 Create `services/analysis-service/llm_client.py`:**

Build an async function `call_llm(prompt: str) -> dict` that:
- POSTs to `https://openrouter.ai/api/v1/chat/completions`
- Uses model `anthropic/claude-3-haiku` (cheap and fast — good for analysis)
- Includes the `Authorization: Bearer {api_key}` header
- Sets `HTTP-Referer: https://github.com/selfops` and `X-Title: SelfOps`
- Uses `tenacity` to retry up to 3 times with exponential backoff on failures
- Always returns a dict — if JSON parsing fails, returns `{"error": "parse_failed", "raw": response_text}`

**5.5 Create `services/analysis-service/main.py`:**

FastAPI app with one endpoint:
- `POST /analyze` — accepts `AnalysisRequest`, calls prompt_builder + llm_client, returns `AnalysisResponse`

If the LLM response cannot be parsed, return a valid `AnalysisResponse` with:
- `summary`: "Analysis failed - raw LLM output stored for review"
- `probable_cause`: "Unknown - manual investigation required"
- `confidence`: 0.0
- `escalate`: true

**5.6 Update the Worker's `analyze_incident` job** to:
1. Load the incident and all its evidence from the database
2. Format metrics evidence as a human-readable text summary
3. Format log evidence as the most recent 20 relevant log lines
4. Build the list of allowed actions from the policy (see Phase 6)
5. Call the analysis service HTTP API
6. Store the response as an `analysis_results` row
7. Update incident status to `ACTION_REQUIRED`
8. Queue a notification job

**5.7 Build and deploy:**
```bash
docker build -t selfops-analysis:latest services/analysis-service/
docker save selfops-analysis:latest | k3s ctr images import -
kubectl apply -f k8s/platform/analysis-service-deployment.yaml
kubectl wait --for=condition=ready pod -l app=selfops-analysis -n platform --timeout=120s
```

### Phase 5 Success Checklist
- [ ] Analysis service pod is Running
- [ ] `POST /analyze` on analysis service returns a valid JSON response
- [ ] Triggering a demo crash creates an incident AND produces an analysis result in the DB
- [ ] Analysis is visible in the frontend incident detail page — Analysis tab
- [ ] LLM parse failures are handled gracefully — worker does not crash or enter CrashLoop
- [ ] OpenRouter API key is read from Kubernetes secret, never from code
- [ ] `git commit -m "feat: complete phase 5 - AI analysis layer"`

---

## Phase 6 — Remediation Engine

### Goal
Operator can click to restart a deployment and it actually happens. Audit trail is complete. Telegram notification is sent.

### Tasks

**6.1 Create the action policy at `services/remediation-runner/policy.py`:**
```python
ALLOWED_ACTIONS = {
    "restart_deployment": {
        "name": "Restart Deployment",
        "description": "Performs a rollout restart of the specified deployment",
        "playbook": "remediation/restart_deployment.yml",
        "safe_for_auto": False,
        "required_params": ["deployment_name", "namespace"],
        "allowed_namespaces": ["platform"],
    },
    "rollout_restart": {
        "name": "Rollout Restart",
        "description": "Graceful rolling restart that replaces pods one at a time",
        "playbook": "remediation/rollout_restart.yml",
        "safe_for_auto": False,
        "required_params": ["deployment_name", "namespace"],
        "allowed_namespaces": ["platform"],
    },
    "scale_up": {
        "name": "Scale Up Replicas",
        "description": "Increases replica count by 1, up to a maximum of 4",
        "playbook": "remediation/scale_up.yml",
        "safe_for_auto": False,
        "required_params": ["deployment_name", "namespace", "max_replicas"],
        "allowed_namespaces": ["platform"],
    },
}

def validate_action(action_id: str, params: dict) -> tuple[bool, str]:
    if action_id not in ALLOWED_ACTIONS:
        return False, f"Action '{action_id}' is not in the allowed list"
    action = ALLOWED_ACTIONS[action_id]
    for param in action["required_params"]:
        if param not in params:
            return False, f"Missing required parameter: {param}"
    namespace = params.get("namespace")
    if namespace and namespace not in action["allowed_namespaces"]:
        return False, f"Namespace '{namespace}' is not allowed for this action"
    return True, "ok"
```

**6.2 Create Ansible playbooks in `infra/ansible/remediation/`:**

`restart_deployment.yml`:
```yaml
- name: Restart Kubernetes deployment
  hosts: localhost
  connection: local
  vars:
    deployment_name: "{{ deployment_name }}"
    namespace: "{{ namespace }}"
  tasks:
    - name: Rollout restart deployment
      command: kubectl rollout restart deployment/{{ deployment_name }} -n {{ namespace }}
      register: restart_result

    - name: Wait for rollout to complete
      command: kubectl rollout status deployment/{{ deployment_name }} -n {{ namespace }} --timeout=120s
      register: status_result
      failed_when: status_result.rc != 0

    - name: Show result
      debug:
        msg: "{{ status_result.stdout }}"
```

Create `rollout_restart.yml` (same as above but with a 30s sleep between pods by using `kubectl rollout restart` with a `--timeout=180s` wait).

Create `scale_up.yml`:
```yaml
- name: Scale up deployment
  hosts: localhost
  connection: local
  vars:
    deployment_name: "{{ deployment_name }}"
    namespace: "{{ namespace }}"
    max_replicas: "{{ max_replicas | default(4) }}"
  tasks:
    - name: Get current replica count
      command: kubectl get deployment {{ deployment_name }} -n {{ namespace }} -o jsonpath='{.spec.replicas}'
      register: current_replicas

    - name: Calculate new replica count
      set_fact:
        new_replicas: "{{ [current_replicas.stdout | int + 1, max_replicas | int] | min }}"

    - name: Scale deployment
      command: kubectl scale deployment {{ deployment_name }} -n {{ namespace }} --replicas={{ new_replicas }}
      when: new_replicas | int > current_replicas.stdout | int

    - name: Report no action needed
      debug:
        msg: "Already at maximum replicas ({{ max_replicas }}), no scaling performed"
      when: new_replicas | int <= current_replicas.stdout | int
```

**6.3 Create `services/remediation-runner/runner.py`:**

A function `run_action(action_id, params, incident_id, action_db_id)` that:
1. Calls `validate_action(action_id, params)`
2. If invalid: updates action status to FAILED, writes audit log, returns
3. Gets the playbook path from `ALLOWED_ACTIONS[action_id]["playbook"]`
4. Runs `ansible-playbook` via subprocess with `-e` extra-vars from params
5. Captures stdout, stderr, and return code
6. Updates action status to SUCCESS or FAILED
7. Writes an audit log entry with the full output

**6.4 Update the API's actions router** to:
- Validate the action against the policy before dispatching
- Create a remediation_action row with status PENDING
- Write an audit log entry: "Action requested by operator"
- Queue the action execution as an ARQ job
- Return the action ID immediately (do not wait for completion)

**6.5 Install ansible in the remediation-runner container:**

In `services/remediation-runner/Dockerfile`:
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y ansible curl && rm -rf /var/lib/apt/lists/*
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY ../../infra/ansible/remediation /app/remediation
CMD ["python", "-m", "arq", "runner.WorkerSettings"]
```

**6.6 Set up Telegram notifications:**

In the Worker's `notify_incident` job, send a formatted message:
```
🚨 *SelfOps Alert*
*Incident:* {title}
*Service:* {service_name} | *Namespace:* {namespace}
*Status:* {status} | *Severity:* {severity}

*Analysis:* {summary}
*Probable cause:* {probable_cause}
*Recommended action:* {recommendation}

_View in dashboard: http://app.YOUR_IP.nip.io/incidents/{id}_
```

Also send a notification when a remediation action completes (success or failure).

### Phase 6 Success Checklist
- [ ] All three Ansible playbooks exist and have correct syntax (`ansible-playbook --syntax-check`)
- [ ] Remediation runner pod is Running
- [ ] Triggering a `/crash` on demo app causes: alert -> incident -> analysis -> Telegram notification
- [ ] Clicking Restart Deployment in the frontend: creates action record, runs Ansible, updates status
- [ ] The completed action (success or failure) appears in the audit log
- [ ] A Telegram notification is sent when the action completes
- [ ] Full end-to-end scenario: crash -> detect -> analyze -> restart -> recovery
- [ ] `git commit -m "feat: complete phase 6 - remediation engine"`

---

## Phase 7 — Polish & Portfolio Presentation

### Tasks

**7.1 Update README.md with:**
- Project name: **SelfOps — AI-Powered Self-Healing Infrastructure**
- One-line description
- Architecture diagram placeholder (add as `docs/architecture.png` if possible to generate)
- Complete tech stack table with reason for each choice
- Live demo URL: `http://app.YOUR_IP.nip.io`
- How to reproduce locally (Docker Compose steps)
- The three demo scenarios with step-by-step instructions

**7.2 Create `scripts/trigger-demo-crash.sh`:**
```bash
#!/bin/bash
echo "Triggering demo app crash..."
DEMO_POD=$(kubectl get pods -n platform -l app=selfops-demo-app -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n platform $DEMO_POD -- curl -s localhost:8080/crash
echo "Done. Watch the SelfOps dashboard for the incident."
```

**7.3 Create `scripts/trigger-demo-cpu.sh`:**
```bash
#!/bin/bash
echo "Triggering CPU stress on demo app..."
DEMO_POD=$(kubectl get pods -n platform -l app=selfops-demo-app -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n platform $DEMO_POD -- curl -s localhost:8080/stress-cpu
echo "Done. CPU alert should fire in ~2 minutes."
```

**7.4 Create `scripts/port-forward.sh`:**
```bash
#!/bin/bash
echo "Starting port forwards for local development..."
kubectl port-forward -n platform svc/selfops-api 8000:8000 &
kubectl port-forward -n platform svc/selfops-frontend 3000:3000 &
kubectl port-forward -n monitoring svc/kube-prom-grafana 3001:80 &
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 &
kubectl port-forward -n monitoring svc/kube-prom-alertmanager 9093:9093 &
echo "All port forwards started."
echo "  API:           http://localhost:8000/api/docs"
echo "  Frontend:      http://localhost:3000"
echo "  Grafana:       http://localhost:3001"
echo "  Prometheus:    http://localhost:9090"
echo "  Alertmanager:  http://localhost:9093"
```

**7.5 Final commit:**
```bash
git add -A
git commit -m "feat: complete phase 7 - polish and portfolio presentation"
git push origin main
```

### Phase 7 Success Checklist
- [ ] README clearly describes the project and how to demo it
- [ ] Demo scripts are executable (`chmod +x scripts/*.sh`)
- [ ] Full end-to-end demo works in under 5 minutes following the README
- [ ] All code is committed and pushed to GitHub
- [ ] No secrets are in git history (check with `git log --all -p | grep -i "api_key\|password\|token"`)
- [ ] `kubectl get pods -A` shows all pods healthy with no restarts

---

## Final Verification

After all phases complete, run this full system check:

```bash
echo "=== Node Status ==="
kubectl get nodes

echo "=== All Pods ==="
kubectl get pods -A

echo "=== Services ==="
kubectl get svc -n platform
kubectl get svc -n monitoring

echo "=== Ingress ==="
kubectl get ingress -A

echo "=== Disk Usage ==="
df -h

echo "=== Memory Usage ==="
free -h

echo "=== API Health ==="
curl -s http://localhost/api/health | python3 -m json.tool

echo "=== Done ==="
```

If everything passes, SelfOps is built. Congratulations.
