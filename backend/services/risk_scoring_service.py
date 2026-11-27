"""Risk rating and score. Pure functions, no I/O.

Rating rules (Agent 4 spec):
    no control found      -> CRITICAL
    coverage < 50%        -> HIGH
    coverage 50-80%       -> MEDIUM
    coverage > 80%        -> LOW
Two documented adjustments, both only ever raise the rating:
    * shall/must (HIGH severity) obligation in the MEDIUM band          -> HIGH
    * Evidence Missing / Control Ineffective on a HIGH severity obligation -> at least MEDIUM
"""
from __future__ import annotations

from dataclasses import dataclass, field

from services.gap_types import GapType, Risk

ORDER = [Risk.LOW, Risk.MEDIUM, Risk.HIGH, Risk.CRITICAL]
# (low, high) of the 0-100 risk score inside each rating
SCORE_BANDS = {Risk.CRITICAL: (90.0, 100.0), Risk.HIGH: (65.0, 89.99), Risk.MEDIUM: (35.0, 64.99), Risk.LOW: (0.0, 34.99)}


@dataclass
class RiskResult:
    rating: str
    score: float
    factors: list[str] = field(default_factory=list)


def coverage_band(coverage: float) -> str:
    if coverage < 50:
        return Risk.HIGH
    if coverage <= 80:
        return Risk.MEDIUM
    return Risk.LOW


def _raise_to(current: str, floor: str) -> str:
    return floor if ORDER.index(floor) > ORDER.index(current) else current


def score_risk(coverage: float, obligation_severity: str | None, gaps: list[str], has_control: bool,
               escalate_high_severity: bool = True) -> RiskResult:
    severity = (obligation_severity or "").upper()
    factors: list[str] = []
    coverage = max(0.0, min(100.0, coverage))

    if not has_control or GapType.MISSING_CONTROL in gaps:
        rating = Risk.CRITICAL
        coverage = 0.0 if not has_control else coverage
        factors.append("No control covers this obligation.")
    else:
        rating = coverage_band(coverage)
        factors.append(f"Coverage {coverage:.0f}% -> {rating} band.")
        if escalate_high_severity and severity == "HIGH" and rating == Risk.MEDIUM:
            rating = Risk.HIGH
            factors.append("Mandatory (shall/must) obligation: MEDIUM raised to HIGH.")
        if severity == "HIGH" and any(g in gaps for g in (GapType.EVIDENCE_MISSING, GapType.CONTROL_INEFFECTIVE)):
            raised = _raise_to(rating, Risk.MEDIUM)
            if raised != rating:
                factors.append("Evidence or effectiveness gap on a mandatory obligation: raised to MEDIUM.")
            rating = raised

    lo, hi = SCORE_BANDS[rating]
    extra = max(0, len([g for g in gaps if g != GapType.NO_GAP]) - 1)
    position = min(1.0, (100.0 - coverage) / 100.0 + 0.05 * extra)
    return RiskResult(rating=rating, score=round(lo + (hi - lo) * position, 2), factors=factors)
