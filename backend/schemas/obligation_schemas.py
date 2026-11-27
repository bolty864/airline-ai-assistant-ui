from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ObligationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clause_ref: str | None
    obligation_text: str
    obligation_type: str | None
    owner_function: str | None
    severity: str | None
    citation: str | None
    confidence_score: float | None = Field(description="0-100")
    target_system: str | None
    mapping_status: str | None = None
    created_at: datetime | None = None


class FailedClause(BaseModel):
    clause_number: str
    error: str


class UsageOut(BaseModel):
    model: str
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embedding_model: str
    embedding_tokens: int = 0
    embedding_cache_hits: int = 0


class ExtractionSummary(BaseModel):
    document_id: int
    doc_code: str
    regulator: str
    status: str = Field(description="COMPLETED | PARTIAL | NO_OBLIGATIONS | SKIPPED_UNCHANGED")
    reprocessed: bool = False
    file_sha256: str
    hash_matches_registry: bool = True
    format: str | None = None
    page_count: int | None = None
    total_clauses: int = 0
    candidate_clauses: int = 0
    skipped_non_mandatory: int = 0
    failed_clauses: list[FailedClause] = []
    obligations_extracted: int = 0
    dropped_low_confidence: int = 0
    duplicates_removed: int = 0
    citations_repaired: int = 0
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    usage: UsageOut | None = None
    duration_ms: int = 0
    mapping_queued: bool = False
    warnings: list[str] = []
    obligations: list[ObligationOut] = []


class ExtractionAccepted(BaseModel):
    document_id: int
    status: str = "ACCEPTED"
    message: str
