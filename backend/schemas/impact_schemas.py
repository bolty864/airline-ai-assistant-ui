from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from schemas.gap_schemas import GapUsageOut


class RemediationTaskOut(BaseModel):
    id: int
    impact_id: int
    task_name: str
    owner_team: str | None = None
    priority: str | None = Field(None, description="Same scale as the risk rating: CRITICAL | HIGH | MEDIUM | LOW")
    due_days: int | None = Field(None, description="Days from today")
    status: str = Field("OPEN", description="OPEN | IN_PROGRESS | DONE | CANCELLED")
    detail: str | None = None
    change_type: str | None = None
    clause_ref: str | None = None
    risk_rating: str | None = None
    created_at: datetime | None = None


class ChangeImpactOut(BaseModel):
    """The Agent 5 contract (change_type ... confidence_score) plus what the UI and reports need."""

    id: int
    document_id: int
    change_type: str = Field(description="NEW_OBLIGATION | MODIFIED_OBLIGATION | REMOVED_OBLIGATION | SEVERITY_CHANGE | "
                                         "RETENTION_CHANGE | REPORTING_CHANGE | SECURITY_REQUIREMENT_CHANGE")
    old_clause: str | None = None
    new_clause: str | None = None
    affected_control: str | None = Field(None, description="Primary control; all of them are in affected_controls")
    affected_system: str | None = Field(None, description="Most critical system; all of them are in affected_systems")
    affected_team: str | None = None
    risk_rating: str = Field(description="CRITICAL | HIGH | MEDIUM | LOW")
    remediation_action: str | None = Field(None, description="First remediation task; the full plan is in `tasks`")
    confidence_score: float = Field(description="0-1")
    clause_ref: str | None = None
    risk_score: float | None = Field(None, description="0-100; orders changes inside a rating")
    summary: str | None = None
    additional_changes: list[str] = []
    affected_controls: list[dict[str, Any]] = []
    affected_systems: list[dict[str, Any]] = []
    affected_teams: list[str] = []
    needs_review: bool = False
    tasks: list[RemediationTaskOut] = []
    details: dict[str, Any] = {}
    assessed_at: datetime | None = None


class ImpactStats(BaseModel):
    total: int = 0
    by_change_type: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    needs_review: int = 0
    tasks_total: int = 0
    tasks_open: int = 0


class ImpactAnalysisSummary(BaseModel):
    document_id: int
    doc_code: str
    regulator: str | None = None
    status: str = Field(description="COMPLETED | PARTIAL | NO_CHANGES | NO_OBLIGATIONS | NO_PREVIOUS_VERSION")
    baseline: str | None = Field(None, description="What the new version was compared with")
    previous_version: str | None = None
    current_version: str | None = None
    overall_risk_rating: str | None = None
    overall_risk_score: float | None = Field(None, description="0-100 compliance risk of the whole change")
    summary: str | None = None
    analyzed: int = Field(0, description="Changes analysed in this run")
    unchanged: int = Field(0, description="Skipped: same change, same context as the last run")
    rules_only: int = Field(0, description="Analysed by rules alone because GPT-4o failed (flagged needs_review)")
    pending_mapping: list[int] = Field([], description="Obligation ids Agent 3 has not finished mapping")
    removed_stale: int = Field(0, description="Impacts of changes that no longer exist, deleted")
    stats: ImpactStats = ImpactStats()
    usage: GapUsageOut | None = None
    duration_ms: int = 0
    warnings: list[str] = []
    impacts: list[ChangeImpactOut] = []


class ImpactAccepted(BaseModel):
    document_id: int
    status: str = "ACCEPTED"
    message: str


class ImpactReport(BaseModel):
    document_id: int
    doc_code: str
    regulator: str | None = None
    status: str = "NOT_ANALYZED"
    baseline: str | None = None
    previous_version: str | None = None
    current_version: str | None = None
    overall_risk_rating: str | None = None
    overall_risk_score: float | None = None
    summary: str | None = None
    pending_mapping: list[int] = []
    analyzed_at: datetime | None = None
    stats: ImpactStats = ImpactStats()
    impacts: list[ChangeImpactOut] = []


class TaskReport(BaseModel):
    document_id: int
    doc_code: str
    total: int = 0
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_team: dict[str, int] = {}
    tasks: list[RemediationTaskOut] = []
