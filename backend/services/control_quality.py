"""Deterministic checks on a control's own health: operating effectiveness, evidence and automation.

These come from the control register, not from GPT, so the same register always gives the same result.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from services.gap_types import AssetView, GapType

# Evidence older than this (days) is stale for a control run at the given frequency
STALE_AFTER_DAYS = {
    "continuous": 7, "daily": 3, "weekly": 14, "monthly": 45, "quarterly": 135,
    "semi-annual": 200, "semiannual": 200, "half-yearly": 200, "annual": 400, "yearly": 400,
}
DEFAULT_STALE_DAYS = 400
# Governance-style controls are manual by nature, so MANUAL on them is not a risk
NON_OPERATIONAL_TYPES = {"governance", "policy", "directive", "oversight"}


@dataclass
class QualityFlag:
    gap_type: str
    control_code: str
    reason: str


def stale_after_days(frequency: str | None) -> int:
    return STALE_AFTER_DAYS.get((frequency or "").strip().lower(), DEFAULT_STALE_DAYS)


def check_control(c: AssetView, now: datetime, require_evidence: bool = True) -> list[QualityFlag]:
    flags: list[QualityFlag] = []
    if c.test_result == "FAILED":
        flags.append(QualityFlag(GapType.CONTROL_INEFFECTIVE, c.code, f"{c.code} failed its last effectiveness test."))
    if require_evidence:
        if not (c.evidence_source or "").strip():
            flags.append(QualityFlag(GapType.EVIDENCE_MISSING, c.code,
                                     f"{c.code} has no evidence source in the control register."))
        elif c.last_evidence_at is not None:
            age = (now - c.last_evidence_at).days
            limit = stale_after_days(c.frequency)
            if age > limit:
                flags.append(QualityFlag(GapType.EVIDENCE_MISSING, c.code,
                                         f"Last evidence for {c.code} is {age} days old (limit {limit} for "
                                         f"{c.frequency or 'unspecified'} controls)."))
    if c.automation_level == "MANUAL" and (c.control_type or "").strip().lower() not in NON_OPERATIONAL_TYPES:
        flags.append(QualityFlag(GapType.MANUAL_PROCESS_RISK, c.code,
                                 f"{c.code} is performed manually and depends on individual execution."))
    return flags


def summarise(flags: list[QualityFlag]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in flags:
        out.setdefault(f.gap_type, []).append(f.reason)
    return out
