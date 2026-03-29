-- 004_pg_diagnostics_evidence.sql
--
-- Expand the evidence_type CHECK constraint to allow two additional types
-- introduced after the initial schema:
--
--   deploy_correlation  — GitHub deploy/change correlation (added in phase 2)
--   database            — PostgreSQL runtime diagnostics (pg_stat_activity)
--
-- PostgreSQL does not support ALTER CONSTRAINT; the constraint must be
-- dropped and re-added.

ALTER TABLE incident_evidence
    DROP CONSTRAINT IF EXISTS incident_evidence_evidence_type_check;

ALTER TABLE incident_evidence
    ADD CONSTRAINT incident_evidence_evidence_type_check
    CHECK (evidence_type IN (
        'metric',
        'log',
        'alert',
        'analysis_input',
        'deploy_correlation',
        'database'
    ));
