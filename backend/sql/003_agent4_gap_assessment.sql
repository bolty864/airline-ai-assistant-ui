-- =====================================================================
-- Agent 4: Compliance Gap Assessment Agent
-- Run AFTER 001 (base) and 002 (Agent 3). Safe to re-run.
-- =====================================================================

-- ---------- Control attributes Agent 4 needs to judge evidence and operating effectiveness ----------
-- Populated from control_registers/controls.json|csv by POST /api/mapping/ingest.
ALTER TABLE controls ADD COLUMN IF NOT EXISTS automation_level VARCHAR(20);   -- AUTOMATED | HYBRID | MANUAL
ALTER TABLE controls ADD COLUMN IF NOT EXISTS evidence_source  TEXT;          -- where audit evidence comes from
ALTER TABLE controls ADD COLUMN IF NOT EXISTS last_evidence_at TIMESTAMP;     -- most recent evidence produced
ALTER TABLE controls ADD COLUMN IF NOT EXISTS test_result      VARCHAR(20);   -- PASSED | FAILED | NOT_TESTED

-- ---------- Agent 4 output: one assessment per obligation ----------
CREATE TABLE IF NOT EXISTS compliance_gap_assessments (
    id SERIAL PRIMARY KEY,
    obligation_id INTEGER NOT NULL UNIQUE REFERENCES compliance_obligations(id) ON DELETE CASCADE,
    mapping_id INTEGER REFERENCES obligation_mappings(id) ON DELETE SET NULL,   -- primary control/policy mapping
    gap_type VARCHAR(100) NOT NULL,            -- primary gap, or 'No Gap'
    risk_rating VARCHAR(20) NOT NULL CHECK (risk_rating IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    coverage_score NUMERIC(5,2) NOT NULL,      -- 0-100
    observation TEXT,
    recommendation TEXT,
    confidence_score NUMERIC(5,2),             -- 0-1 (as in the Agent 4 contract)
    created_at TIMESTAMP DEFAULT NOW(),
    -- additions
    updated_at TIMESTAMP DEFAULT NOW(),
    risk_score NUMERIC(5,2),                   -- 0-100, orders findings inside a rating
    owner_function VARCHAR(100),
    additional_gaps TEXT[] NOT NULL DEFAULT '{}',
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    details JSONB,                             -- parameter checks, risk factors, adjustments, assets considered
    input_fingerprint CHAR(64),                -- hash of everything the assessment depends on (skip if unchanged)
    source_mapped_at TIMESTAMP,                -- obligations.mapped_at when assessed (stale detection)
    model_used VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_gap_risk ON compliance_gap_assessments (risk_rating);
CREATE INDEX IF NOT EXISTS idx_gap_type ON compliance_gap_assessments (gap_type);
CREATE INDEX IF NOT EXISTS idx_gap_mapping ON compliance_gap_assessments (mapping_id);

-- ---------- Read model for dashboards / Agents 5 and 8 ----------
CREATE OR REPLACE VIEW v_compliance_gaps AS
SELECT
    rd.id            AS document_id,
    rd.doc_code,
    rd.regulator,
    o.id             AS obligation_id,
    o.clause_ref,
    o.obligation_text,
    o.severity       AS obligation_severity,
    g.id             AS assessment_id,
    g.gap_type,
    g.additional_gaps,
    g.risk_rating,
    g.risk_score,
    g.coverage_score,
    g.observation,
    g.recommendation,
    g.confidence_score,
    g.needs_review,
    g.owner_function,
    g.updated_at     AS assessed_at,
    (o.mapped_at IS DISTINCT FROM g.source_mapped_at) AS stale
FROM compliance_gap_assessments g
JOIN compliance_obligations o ON o.id = g.obligation_id
JOIN regulatory_documents rd  ON rd.id = o.document_id;
