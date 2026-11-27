"""Vocabulary and plain data objects shared by the Agent 5 services."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class ChangeType:
    NEW = "NEW_OBLIGATION"
    MODIFIED = "MODIFIED_OBLIGATION"
    REMOVED = "REMOVED_OBLIGATION"
    SEVERITY = "SEVERITY_CHANGE"
    RETENTION = "RETENTION_CHANGE"
    REPORTING = "REPORTING_CHANGE"
    SECURITY = "SECURITY_REQUIREMENT_CHANGE"

    ALL = [NEW, MODIFIED, REMOVED, SEVERITY, RETENTION, REPORTING, SECURITY]


class Domain:
    """What the clause is about. Drives the risk matrix and the remediation templates."""

    RETENTION = "RETENTION"
    REPORTING = "REPORTING"
    SECURITY = "SECURITY"
    OTHER = "OTHER"


@dataclass
class ObligationRec:
    """An obligation on either side of the comparison (a live row, or a row of the previous version)."""

    text: str
    clause_ref: str | None = None
    severity: str | None = None
    obligation_type: str | None = None
    owner_function: str | None = None
    target_system: str | None = None
    citation: str | None = None
    confidence: float | None = None            # extraction confidence, 0-100
    embedding: Any = None                      # numpy array or None
    obligation_id: int | None = None           # set for live obligations
    snapshot_id: int | None = None             # set for rows of the previous version
    mapping_status: str | None = None
    mapped_at: datetime | None = None
    assets: list[dict] = field(default_factory=list)   # [{type, code, name, owner, link_type, relevance}]


@dataclass
class DiffEntry:
    change_type: str
    domain: str
    old: ObligationRec | None
    new: ObligationRec | None
    similarity: float = 0.0
    minor: bool = False                        # wording only: no number, modal verb or negation changed
    additional_changes: list[str] = field(default_factory=list)
    quantity_changes: list[dict] = field(default_factory=list)   # [{"unit": "year", "old": ["3"], "new": ["5"]}]
    modal_change: tuple[list[str], list[str]] | None = None
    severity_old: str | None = None
    severity_new: str | None = None
    key: str = ""

    @property
    def clause_ref(self) -> str | None:
        return (self.new or self.old).clause_ref if (self.new or self.old) else None


@dataclass
class ImpactContext:
    """Everything known about what a change touches. Candidates come from Agent 3's mappings and the registers."""

    controls: list[Any] = field(default_factory=list)        # AssetView (CONTROL)
    systems: list[Any] = field(default_factory=list)         # AssetView (SYSTEM)
    policies: list[dict] = field(default_factory=list)       # [{code, name}]
    direct_codes: set[str] = field(default_factory=set)      # Agent 3 linked these as DIRECT: always kept
    obligation_owner: str | None = None
    gap: dict | None = None                                  # Agent 4 result for the new obligation


@dataclass
class ChangeAnalysis:
    """Validated GPT-4o output for one change."""

    summary: str
    material: bool
    change_type: str
    control_codes: list[str]
    system_codes: list[str]
    teams: list[str]
    actions: list[dict]                        # [{task_name, owner_team, detail}]
    confidence: float                          # 0-1
    warnings: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class TaskDraft:
    name: str
    owner_team: str
    priority: str
    due_days: int
    key: str
    detail: str = ""


@dataclass
class ImpactDraft:
    """A fully assembled impact, ready to store."""

    entry: DiffEntry
    change_type: str
    clause_ref: str | None
    new_obligation_id: int | None
    old_clause: str
    new_clause: str
    summary: str
    controls: list[dict]
    systems: list[dict]
    teams: list[str]
    risk_rating: str
    risk_score: float
    confidence: float
    needs_review: bool
    additional_changes: list[str]
    tasks: list[TaskDraft]
    details: dict[str, Any]
    fingerprint: str
    model_used: str | None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
