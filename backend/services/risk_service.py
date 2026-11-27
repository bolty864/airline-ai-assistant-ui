"""Risk rating of a regulatory change, and the overall risk of a document. Pure functions, no I/O.

Matrix (Agent 5 spec) with the choices the spec leaves open:
    critical system impacted            -> CRITICAL   (only for changes that tighten a requirement)
    security requirement changed        -> HIGH
    retention period changed            -> HIGH       (the spec's own sample: 3 -> 5 years = HIGH)
    reporting requirement changed       -> MEDIUM
    minor wording update                -> LOW
Others: new obligation MEDIUM (HIGH in retention/security), other modification MEDIUM, severity raised MEDIUM,
severity lowered or obligation removed LOW. Only ever raised by: an existing Agent 4 gap rated HIGH/CRITICAL (at least
HIGH), a change with no control at all (at least HIGH), a raised severity on top of a text change (at least MEDIUM).
Overall rating = the highest individual rating; the overall score rises inside that rating with the number of changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from services.gap_types import Risk
from services.impact_types import ChangeType, DiffEntry, Domain
from services.risk_scoring_service import ORDER, SCORE_BANDS

_SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
_OVERALL_WEIGHT = {Risk.CRITICAL: 0.50, Risk.HIGH: 0.30, Risk.MEDIUM: 0.12, Risk.LOW: 0.03}


@dataclass
class ImpactRisk:
    rating: str
    score: float
    factors: list[str] = field(default_factory=list)


def severity_raised(entry: DiffEntry) -> bool:
    return (_SEVERITY_RANK.get(entry.severity_new or "", 0) > _SEVERITY_RANK.get(entry.severity_old or "", 0)
            and entry.old is not None and entry.new is not None)


def severity_lowered(entry: DiffEntry) -> bool:
    return (_SEVERITY_RANK.get(entry.severity_new or "", 0) < _SEVERITY_RANK.get(entry.severity_old or "", 0)
            and entry.old is not None and entry.new is not None)


def tightens(entry: DiffEntry) -> bool:
    """True when the change can force the airline to do more than before."""
    if entry.change_type == ChangeType.REMOVED or entry.minor:
        return False
    if entry.change_type == ChangeType.SEVERITY:
        return severity_raised(entry)
    return True


def _raise_to(current: str, floor: str) -> str:
    return floor if ORDER.index(floor) > ORDER.index(current) else current


def rate_impact(entry: DiffEntry, systems: list[dict], has_controls: bool, gap: dict | None) -> ImpactRisk:
    factors: list[str] = []
    boosts = 0
    ct, domain = entry.change_type, entry.domain

    if ct == ChangeType.REMOVED:
        rating = Risk.LOW
        factors.append("Obligation removed: the requirement is relaxed.")
    elif entry.minor:
        rating = Risk.LOW
        factors.append("Wording-only update: no number, modal verb or negation changed.")
    elif ct == ChangeType.SEVERITY:
        rating = Risk.MEDIUM if severity_raised(entry) else Risk.LOW
        factors.append(f"Severity {entry.severity_old} -> {entry.severity_new}.")
    elif ct == ChangeType.SECURITY:
        rating = Risk.HIGH
        factors.append("Security requirement changed.")
    elif ct == ChangeType.RETENTION:
        rating = Risk.HIGH
        factors.append("Retention requirement changed.")
    elif ct == ChangeType.REPORTING:
        rating = Risk.MEDIUM
        factors.append("Reporting requirement changed.")
    elif ct == ChangeType.NEW:
        rating = Risk.HIGH if domain in (Domain.SECURITY, Domain.RETENTION) else Risk.MEDIUM
        factors.append(f"New obligation ({domain.lower()}).")
    else:
        rating = Risk.MEDIUM
        factors.append("Obligation modified.")

    if tightens(entry):
        critical = [s["name"] for s in systems if (s.get("criticality") or "").upper() == "CRITICAL"]
        if critical:
            rating = Risk.CRITICAL
            boosts += 1
            factors.append(f"Critical system impacted: {', '.join(critical[:3])}.")
        if gap and gap.get("risk_rating") in (Risk.CRITICAL, Risk.HIGH):
            rating = _raise_to(rating, Risk.HIGH)
            boosts += 1
            factors.append(f"Existing gap on this obligation ({gap.get('gap_type')}, {gap.get('risk_rating')}).")
        if not has_controls:
            rating = _raise_to(rating, Risk.HIGH)
            boosts += 1
            factors.append("No control covers this requirement.")
        if len(systems) > 2:
            boosts += 1
            factors.append(f"{len(systems)} systems affected.")
        if severity_raised(entry) and ct != ChangeType.SEVERITY:
            rating = _raise_to(rating, Risk.MEDIUM)
            boosts += 1
            factors.append(f"Severity also raised {entry.severity_old} -> {entry.severity_new}.")

    lo, hi = SCORE_BANDS[rating]
    position = min(1.0, 0.30 + 0.15 * boosts) if rating != Risk.LOW else 0.15
    return ImpactRisk(rating=rating, score=round(lo + (hi - lo) * position, 2), factors=factors)


def overall_risk(ratings: list[str]) -> tuple[str, float]:
    """(rating, 0-100 score) for a whole document: highest rating, score grows with the number of changes."""
    if not ratings:
        return Risk.LOW, 0.0
    top = max(ratings, key=ORDER.index)
    combined = 1.0
    for r in ratings:
        combined *= 1.0 - _OVERALL_WEIGHT[r]
    lo, hi = SCORE_BANDS[top]
    return top, round(lo + (hi - lo) * (1.0 - combined), 2)
