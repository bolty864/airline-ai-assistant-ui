"""Vocabulary and plain data objects shared by the Agent 4 services."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class GapType:
    MISSING_CONTROL = "Missing Control"
    PARTIAL_COVERAGE = "Partial Coverage"
    CONTROL_INEFFECTIVE = "Control Ineffective"
    EVIDENCE_MISSING = "Evidence Missing"
    MANUAL_PROCESS_RISK = "Manual Process Risk"
    POLICY_MISALIGNMENT = "Policy Misalignment"
    NO_GAP = "No Gap"          # compliant: stored so dashboards can compute coverage


class Risk:
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# Which gap becomes the primary one when an obligation has several (most urgent first)
GAP_PRIORITY: list[str] = [
    GapType.MISSING_CONTROL, GapType.CONTROL_INEFFECTIVE, GapType.PARTIAL_COVERAGE,
    GapType.POLICY_MISALIGNMENT, GapType.EVIDENCE_MISSING, GapType.MANUAL_PROCESS_RISK,
]
# Gaps GPT may report. Missing Control and Evidence Missing are decided by rules, never by the model.
LLM_GAP_TYPES: list[str] = [
    GapType.PARTIAL_COVERAGE, GapType.CONTROL_INEFFECTIVE, GapType.POLICY_MISALIGNMENT, GapType.MANUAL_PROCESS_RISK,
]


def order_gaps(types: Iterable[str]) -> list[str]:
    """Unique, known gap types, most urgent first."""
    present = set(types)
    return [g for g in GAP_PRIORITY if g in present]


@dataclass
class ObligationView:
    id: int
    text: str
    regulator: str
    document_title: str
    clause_ref: str | None = None
    citation: str | None = None
    obligation_type: str | None = None
    severity: str | None = None               # HIGH / MEDIUM / LOW from Agent 2's rules
    owner_function: str | None = None
    target_system: str | None = None
    confidence: float | None = None           # Agent 2 extraction confidence, 0-100
    mapping_status: str | None = None
    mapped_at: datetime | None = None


@dataclass
class AssetView:
    """A policy section, control or system mapped to an obligation by Agent 3."""

    mapping_id: int
    target_type: str                          # POLICY_SECTION | CONTROL | SYSTEM
    code: str
    name: str
    link_type: str = "SUPPORTING"
    relevance: float = 0.0                    # Agent 3 relevance, 0-100 (NOT coverage)
    review_status: str = "PROPOSED"
    key: str = ""                             # short id shown to the LLM: P1 / C1 / S1
    # policy section
    doc_code: str | None = None
    section_ref: str | None = None
    heading: str | None = None
    text: str = ""
    current_provision: str | None = None
    # control
    description: str = ""
    control_type: str | None = None
    frequency: str | None = None
    owner_function: str | None = None
    automation_level: str | None = None
    evidence_source: str | None = None
    last_evidence_at: datetime | None = None
    test_result: str | None = None
    # system
    data_categories: list[str] = field(default_factory=list)
    criticality: str | None = None            # CRITICAL | HIGH | MEDIUM | LOW

    @property
    def is_control(self) -> bool:
        return self.target_type == "CONTROL"

    @property
    def evidence_text(self) -> str:
        """Everything the model was shown for this asset (used to check its quotes are real)."""
        return " ".join(filter(None, [self.name, self.heading, self.text, self.current_provision, self.description]))


@dataclass
class ParameterCheck:
    parameter: str
    required: str
    actual: str
    met: bool
    source_ref: str = ""
    actual_quote: str = ""
    verified: bool = True                     # False if the quote is not found in the evidence


@dataclass
class LLMAssessment:
    applicable_control_found: bool
    parameters: list[ParameterCheck]
    coverage: float                           # 0-100
    gap_types: list[str]
    primary_ref: str | None
    supporting_refs: list[str]
    observation: str
    recommendation: str
    confidence: float                         # 0-1
    warnings: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class Finding:
    """The final, validated assessment of one obligation (what gets stored)."""

    obligation_id: int
    mapping_id: int | None
    gap_type: str
    additional_gaps: list[str]
    risk_rating: str
    risk_score: float
    coverage: float
    observation: str
    recommendation: str
    confidence: float
    owner_function: str | None
    needs_review: bool
    details: dict[str, Any]
    fingerprint: str
    source_mapped_at: datetime | None
    model_used: str | None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
