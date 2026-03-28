-- Migration 002: add structured_analysis column to analysis_results
-- Adds the v3 structured output (hypotheses, evidence, action_plan) as a
-- nullable JSONB column.  Existing rows remain valid with NULL in this column.

ALTER TABLE analysis_results
    ADD COLUMN IF NOT EXISTS structured_analysis JSONB;

-- Partial index: only index rows that have structured analysis populated
-- (avoids index bloat from pre-migration rows).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_results_has_structured
    ON analysis_results ((structured_analysis IS NOT NULL))
    WHERE structured_analysis IS NOT NULL;

-- Composite lookup index used by the frontend agent-trace / analysis detail views.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_results_incident_created
    ON analysis_results (incident_id, created_at DESC);
