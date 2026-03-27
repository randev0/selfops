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
