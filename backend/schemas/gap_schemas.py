from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GapAssessmentOut(BaseModel):
    """Matches the Agent 4 contract (obligation_id ... confidence_score) plus fields the UI and Agent 5 need."""

    id: int
    obligation_id: int
    mapping_id: int | None = None
    gap_type: str = Field(description="Primary gap, or 'No Gap' when compliant")
    additional_gaps: list[str] = []
    risk_rating: str = Field(description="CRITICAL | HIGH | MEDIUM | LOW")
    risk_score: float | None = Field(None, description="0-100; orders findings inside a rating")
    coverage_score: float = Field(description="0-100")
    observation: str
    recommendation: str
    confidence_score: float = Field(description="0-1")
    owner_function: str | None = None
    needs_review: bool = Field(False, description="Low confidence or based on the absence of a mapping")
    stale: bool = Field(False, description="Agent 3 re-mapped this obligation after it was assessed")
    clause_ref: str | None = None
    obligation_text: str
    obligation_severity: str | None = None
    details: dict[str, Any] = {}
    assessed_at: datetime | None = None


class GapStats(BaseModel):
    total: int = 0
    compliant: int = 0
    with_gaps: int = 0
    by_risk: dict[str, int] = {}
    by_gap_type: dict[str, int] = {}
    average_coverage: float | None = None
    needs_review: int = 0
    stale: int = 0


class FailedObligation(BaseModel):
    obligation_id: int
    error: str


class GapUsageOut(BaseModel):
    model: str
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class GapAnalysisSummary(BaseModel):
    document_id: int
    doc_code: str
    status: str = Field(description="COMPLETED | PARTIAL | NO_OBLIGATIONS | PENDING_MAPPING | SKIPPED_UNCHANGED")
    total_obligations: int = 0
    assessed: int = Field(0, description="Obligations (re)assessed in this run")
    llm_assessed: int = 0
    unchanged: int = Field(0, description="Skipped because nothing they depend on changed")
    pending_mapping: list[int] = Field([], description="Obligation ids Agent 3 has not finished mapping")
    failed: list[FailedObligation] = []
    stats: GapStats = GapStats()
    usage: GapUsageOut | None = None
    duration_ms: int = 0
    warnings: list[str] = []
    assessments: list[GapAssessmentOut] = []


class GapAnalysisAccepted(BaseModel):
    document_id: int
    status: str = "ACCEPTED"
    message: str


class GapReport(BaseModel):
    document_id: int
    doc_code: str
    stats: GapStats
    assessments: list[GapAssessmentOut]
