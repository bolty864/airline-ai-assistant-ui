from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from schemas.obligation_schemas import ExtractionSummary, ObligationOut


class IngestRequest(BaseModel):
    doc_code: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9_\-.]+$")
    filename: str = Field(min_length=3, max_length=255)
    regulator: str = Field(min_length=2, max_length=50)
    title: str
    source_url: str
    wait: bool = Field(False, description="Run Agents 2+3 before responding (otherwise they run in the background)")


class IngestResult(BaseModel):
    document_id: int
    doc_code: str
    event: str = Field(description="NEW_DOC | DOC_UPDATED | DOC_UNCHANGED")
    changed: bool
    sha256_hash: str
    version_tag: str | None
    blob_path: str
    format: str


class IngestResponse(IngestResult):
    message: str
    extraction: ExtractionSummary | None = None
    extraction_scheduled: bool = False


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_code: str
    filename: str
    regulator: str
    title: str
    source_url: str
    sha256_hash: str
    version_tag: str | None
    status: str | None
    last_verified_at: datetime | None
    updated_at: datetime | None
    obligation_count: int = 0


class DocumentList(BaseModel):
    total: int
    documents: list[DocumentOut]


class DocumentObligations(BaseModel):
    doc_code: str
    status: str | None
    obligations_count: int
    obligations: list[ObligationOut]


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    doc_code: str
    details: dict[str, Any] | None
    created_at: datetime | None


class AuditLogList(BaseModel):
    logs: list[AuditLogOut]


class HealAction(BaseModel):
    doc_code: str
    reason: str
    outcome: str = Field(description="SELF_HEALED | HEAL_FAILED")
    source_changed: bool = False
    error: str | None = None


class ScanResult(BaseModel):
    scanned: int
    healthy: int
    healed: int
    failed: int
    actions: list[HealAction] = []
    scan_duration_ms: int = 0
    skipped: bool = Field(False, description="True if another scan was already running")


class CrawlTriggerRequest(BaseModel):
    regulators: list[str] = ["DGCA", "CERT-IN"]
    max_items: int = Field(2, ge=1, le=20)


class CrawlResponse(BaseModel):
    message: str
    targets: list[str]
    not_supported: list[str] = []
    total_processed: int
    ingested_documents: dict[str, list[dict[str, Any]]]


class SimulateDeleteRequest(BaseModel):
    doc_code: str


class HealthResponse(BaseModel):
    status: str
    database_connected: bool
    blob_storage_connected: bool
    storage_mode: str
    watchdog_active: bool
    watchdog_interval_seconds: int
    llm_configured: bool
    timestamp: datetime
