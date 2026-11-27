-- Agents 1 & 2 base schema (matches what the team already has; safe to re-run).
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS regulatory_documents (
    id SERIAL PRIMARY KEY,
    doc_code VARCHAR(100) UNIQUE NOT NULL,
    filename VARCHAR(255) NOT NULL,
    regulator VARCHAR(50) NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    blob_path TEXT NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    version_tag VARCHAR(50) DEFAULT 'v1.0',
    status VARCHAR(30) DEFAULT 'ACTIVE',
    last_verified_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compliance_obligations (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES regulatory_documents(id) ON DELETE CASCADE,
    clause_ref VARCHAR(100),
    obligation_text TEXT NOT NULL,
    target_system VARCHAR(100),
    severity VARCHAR(20),
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_audit_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    doc_code VARCHAR(100) NOT NULL,
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE compliance_obligations ADD COLUMN IF NOT EXISTS obligation_type VARCHAR(100);
ALTER TABLE compliance_obligations ADD COLUMN IF NOT EXISTS owner_function VARCHAR(100);
ALTER TABLE compliance_obligations ADD COLUMN IF NOT EXISTS citation TEXT;
ALTER TABLE compliance_obligations ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(5,2);

CREATE INDEX IF NOT EXISTS idx_obligations_document ON compliance_obligations (document_id);
CREATE INDEX IF NOT EXISTS idx_audit_doc_event ON agent_audit_logs (doc_code, event_type, id DESC);
