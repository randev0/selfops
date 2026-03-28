-- Phase 1: Agentic Investigation Engine
-- Adds investigation_log to store the ReAct agent's step-by-step thought chain
ALTER TABLE analysis_results
    ADD COLUMN IF NOT EXISTS investigation_log JSONB;
