-- =====================================================================
-- Agent 3: Policy & Control Mapping Agent
-- Run AFTER the Agent 1/2 schema (regulatory_documents, compliance_obligations,
-- agent_audit_logs). Safe to re-run.
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------- Internal enterprise repository (Policies, SOPs, Standards) ----------
CREATE TABLE IF NOT EXISTS enterprise_documents (
    id SERIAL PRIMARY KEY,
    doc_code VARCHAR(100) UNIQUE NOT NULL,        -- e.g. 'PASSENGER_DATA_POLICY'
    doc_type VARCHAR(30) NOT NULL,                -- POLICY, SOP, AUDIT_PROCEDURE, SECURITY_STANDARD
    title TEXT NOT NULL,
    filename VARCHAR(255) NOT NULL,
    blob_path TEXT NOT NULL,
    version_tag VARCHAR(50) DEFAULT 'v1.0',
    sha256_hash VARCHAR(64) NOT NULL,             -- skip re-indexing unchanged files
    status VARCHAR(30) DEFAULT 'ACTIVE',          -- ACTIVE, ARCHIVED
    indexed_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Section-level chunks: mapping happens at clause/section granularity, not whole docs
CREATE TABLE IF NOT EXISTS enterprise_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES enterprise_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    section_ref VARCHAR(50),                      -- e.g. '4.2'
    heading TEXT,
    content TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    embedding vector(1536),
    content_tsv tsvector GENERATED ALWAYS AS
        (to_tsvector('english', coalesce(heading, '') || ' ' || content)) STORED,
    UNIQUE (document_id, chunk_index)
);

-- ---------- Systems & control register ----------
CREATE TABLE IF NOT EXISTS systems (
    id SERIAL PRIMARY KEY,
    system_code VARCHAR(100) UNIQUE NOT NULL,     -- e.g. 'APIS_SCHEDULER'
    name VARCHAR(200) NOT NULL,
    description TEXT,
    aliases TEXT[] DEFAULT '{}',
    data_categories TEXT[] DEFAULT '{}',
    owner_function VARCHAR(100),
    status VARCHAR(30) DEFAULT 'ACTIVE',
    embedding vector(1536),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS controls (
    id SERIAL PRIMARY KEY,
    control_code VARCHAR(50) UNIQUE NOT NULL,     -- e.g. 'CTRL-001'
    name VARCHAR(200) NOT NULL,
    description TEXT,
    control_type VARCHAR(50),                     -- Preventive / Detective / Corrective
    owner_function VARCHAR(100),
    frequency VARCHAR(50),
    policy_doc_code VARCHAR(100),                 -- policy the control implements
    status VARCHAR(30) DEFAULT 'ACTIVE',
    embedding vector(1536),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS control_system_links (
    control_id INTEGER REFERENCES controls(id) ON DELETE CASCADE,
    system_id  INTEGER REFERENCES systems(id)  ON DELETE CASCADE,
    PRIMARY KEY (control_id, system_id)
);

-- ---------- Agent 3 output ----------
CREATE TABLE IF NOT EXISTS obligation_mappings (
    id SERIAL PRIMARY KEY,
    obligation_id INTEGER NOT NULL REFERENCES compliance_obligations(id) ON DELETE CASCADE,
    target_type VARCHAR(20) NOT NULL,             -- POLICY_SECTION, CONTROL, SYSTEM
    target_id INTEGER NOT NULL,
    target_code VARCHAR(200) NOT NULL,            -- 'PASSENGER_DATA_POLICY#4.2', 'CTRL-001', 'APIS_SCHEDULER'
    target_doc_code VARCHAR(100),                 -- owning policy doc (for POLICY_SECTION / CONTROL)
    link_type VARCHAR(20) NOT NULL,               -- DIRECT, SUPPORTING, CONTEXTUAL
    relevance_score NUMERIC(5,2) NOT NULL,        -- 0-100, LLM confidence
    vector_similarity NUMERIC(5,4),
    current_provision TEXT,                       -- verbatim existing text, input for Gap Agent
    rationale TEXT,
    model_used VARCHAR(100),
    review_status VARCHAR(20) DEFAULT 'PROPOSED', -- PROPOSED, CONFIRMED, REJECTED
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (obligation_id, target_type, target_id)
);

-- Re-embedding the same text costs nothing after the first time (self-heal re-runs!)
CREATE TABLE IF NOT EXISTS embedding_cache (
    content_hash CHAR(64) NOT NULL,
    model VARCHAR(100) NOT NULL,
    embedding vector(1536) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (content_hash, model)
);

-- Work queue columns on Agent 2's table. New / re-processed obligations default to PENDING,
-- so a self-heal (CASCADE delete + re-insert) automatically triggers re-mapping.
ALTER TABLE compliance_obligations ADD COLUMN IF NOT EXISTS mapping_status VARCHAR(20) DEFAULT 'PENDING';
ALTER TABLE compliance_obligations ADD COLUMN IF NOT EXISTS mapped_at TIMESTAMP;
ALTER TABLE compliance_obligations ADD COLUMN IF NOT EXISTS mapping_model VARCHAR(100);
-- mapping_status: PENDING, MAPPING, MAPPED, NEEDS_REVIEW, UNMAPPED, ERROR

-- ---------- Indexes ----------
CREATE INDEX IF NOT EXISTS idx_chunks_embedding   ON enterprise_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv         ON enterprise_chunks USING gin (content_tsv);
CREATE INDEX IF NOT EXISTS idx_controls_embedding ON controls USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_systems_embedding  ON systems  USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_obligations_embedding ON compliance_obligations USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_obligations_mapping_status ON compliance_obligations (mapping_status);
CREATE INDEX IF NOT EXISTS idx_mappings_obligation ON obligation_mappings (obligation_id);
CREATE INDEX IF NOT EXISTS idx_mappings_target     ON obligation_mappings (target_type, target_id);

-- ---------- Read model for Gap Analysis Agent (4) and the UI ----------
CREATE OR REPLACE VIEW v_obligation_impact AS
SELECT
    o.id              AS obligation_id,
    rd.doc_code       AS regulation_doc_code,
    rd.regulator,
    o.clause_ref,
    o.obligation_text,
    o.severity,
    o.owner_function  AS obligation_owner,
    m.target_type,
    m.target_code,
    m.target_doc_code,
    COALESCE(ed.title, c.name, s.name) AS target_name,
    ec.section_ref,
    ec.heading        AS section_heading,
    m.link_type,
    m.relevance_score,
    m.vector_similarity,
    m.current_provision,
    m.rationale,
    m.review_status,
    m.model_used,
    m.created_at
FROM obligation_mappings m
JOIN compliance_obligations o ON o.id = m.obligation_id
JOIN regulatory_documents rd  ON rd.id = o.document_id
LEFT JOIN enterprise_chunks ec    ON m.target_type = 'POLICY_SECTION' AND ec.id = m.target_id
LEFT JOIN enterprise_documents ed ON ed.id = ec.document_id
LEFT JOIN controls c ON m.target_type = 'CONTROL' AND c.id = m.target_id
LEFT JOIN systems  s ON m.target_type = 'SYSTEM'  AND s.id = m.target_id;
