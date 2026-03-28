-- Phase 2: GitOps & CI/CD Remediation
-- Adds PENDING_MERGE action status and GitOps fields to remediation_actions

-- New action status for PRs awaiting merge
ALTER TYPE action_status ADD VALUE IF NOT EXISTS 'PENDING_MERGE';

-- GitOps columns on remediation_actions
ALTER TABLE remediation_actions
    ADD COLUMN IF NOT EXISTS remediation_strategy TEXT NOT NULL DEFAULT 'DIRECT_ACTION',
    ADD COLUMN IF NOT EXISTS pr_url              TEXT,
    ADD COLUMN IF NOT EXISTS pr_number           INTEGER,
    ADD COLUMN IF NOT EXISTS pr_branch           TEXT,
    ADD COLUMN IF NOT EXISTS patch_content       TEXT,
    ADD COLUMN IF NOT EXISTS patch_file_path     TEXT;
