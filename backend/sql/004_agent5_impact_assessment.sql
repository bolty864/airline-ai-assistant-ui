-- =====================================================================
-- Agent 5: Regulatory Change Impact & Remediation Agent
-- Run AFTER 001, 002 and 003. Safe to re-run.
-- =====================================================================

-- Systems need a criticality so the risk matrix can tell "critical systems impacted" (CRITICAL/HIGH/MEDIUM/LOW).
-- Populated from control_registers/systems.json by POST /api/mapping/ingest.
ALTER TABLE systems ADD COLUMN IF NOT EXISTS criticality VARCHAR(20);

-- ---------- "Previous regulation": obligations of the previous version of each document ----------
-- Agent 2 replaces a document's obligations when a new version is extracted. Just before it does, the old rows
-- (with the controls / systems they were mapped to) are copied here. Agent 5 diffs the newest snapshot against
-- the current obligations.
CREATE TABLE IF NOT EXISTS regulation_obligation_versions (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES regulatory_documents(id) ON DELETE CASCADE,
    generation INTEGER NOT NULL,                  -- 1, 2, 3 ... per document; highest = the immediately previous version
    clause_ref VARCHAR(100),
    obligation_text TEXT NOT NULL,
    obligation_type VARCHAR(100),
    owner_function VARCHAR(100),
    severity VARCHAR(20),
    target_system VARCHAR(100),
    citation TEXT,
    confidence_score NUMERIC(5,2),
    embedding vector(1536),
    mapped_assets JSONB NOT NULL DEFAULT '[]',    -- [{type, code, name, owner, link_type, relevance}] as mapped by Agent 3
    superseded_by_hash VARCHAR(64),               -- sha256 of the file that replaced this version
    superseded_by_version VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_obl_versions_doc ON regulation_obligation_versions (document_id, generation);

-- ---------- Agent 5 output: one row per detected change ----------
CREATE TABLE IF NOT EXISTS regulation_change_impacts (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES regulatory_documents(id) ON DELETE CASCADE,
    change_type VARCHAR(100) NOT NULL,
    old_clause TEXT,
    new_clause TEXT,
    affected_control TEXT,                        -- primary control; all of them are in affected_controls
    affected_system TEXT,                         -- primary (most critical) system
    affected_team TEXT,                           -- primary owner team
    risk_rating VARCHAR(20) NOT NULL CHECK (risk_rating IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    remediation_action TEXT,                      -- first remediation task; all of them are in remediation_tasks
    confidence_score NUMERIC(5,2),                -- 0-1
    created_at TIMESTAMP DEFAULT NOW(),
    -- additions
    updated_at TIMESTAMP DEFAULT NOW(),
    impact_key CHAR(32) NOT NULL,                 -- stable id of the change (old text + new text), keeps task status across re-runs
    clause_ref VARCHAR(100),
    new_obligation_id INTEGER REFERENCES compliance_obligations(id) ON DELETE SET NULL,
    risk_score NUMERIC(5,2),
    summary TEXT,
    additional_changes TEXT[] NOT NULL DEFAULT '{}',
    affected_controls JSONB NOT NULL DEFAULT '[]',
    affected_systems JSONB NOT NULL DEFAULT '[]',
    affected_teams JSONB NOT NULL DEFAULT '[]',
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    details JSONB,
    fingerprint CHAR(64),                         -- hash of every input; unchanged impacts are not re-analysed
    model_used VARCHAR(100),
    UNIQUE (document_id, impact_key)
);
CREATE INDEX IF NOT EXISTS idx_impacts_doc_risk ON regulation_change_impacts (document_id, risk_rating);

CREATE TABLE IF NOT EXISTS remediation_tasks (
    id SERIAL PRIMARY KEY,
    impact_id INTEGER NOT NULL REFERENCES regulation_change_impacts(id) ON DELETE CASCADE,
    task_name TEXT NOT NULL,
    owner_team VARCHAR(100),
    priority VARCHAR(20),
    due_days INTEGER,
    status VARCHAR(20) DEFAULT 'OPEN',            -- OPEN, IN_PROGRESS, DONE, CANCELLED
    created_at TIMESTAMP DEFAULT NOW(),
    -- additions
    task_key CHAR(32) NOT NULL,
    detail TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (impact_id, task_key)
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON remediation_tasks (status, priority);

-- ---------- One summary row per document: overall compliance risk ----------
CREATE TABLE IF NOT EXISTS regulation_impact_runs (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL UNIQUE REFERENCES regulatory_documents(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL,                  -- COMPLETED, PARTIAL, NO_CHANGES, NO_OBLIGATIONS, NO_PREVIOUS_VERSION
    baseline VARCHAR(200),                        -- what the new version was compared with
    previous_version VARCHAR(50),
    current_version VARCHAR(50),
    total_changes INTEGER NOT NULL DEFAULT 0,
    by_change_type JSONB NOT NULL DEFAULT '{}',
    by_risk JSONB NOT NULL DEFAULT '{}',
    overall_risk_score NUMERIC(5,2),
    overall_risk_rating VARCHAR(20),
    summary TEXT,
    pending_mapping INTEGER[] NOT NULL DEFAULT '{}',
    model_used VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
