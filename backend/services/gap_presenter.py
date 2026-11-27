"""ORM rows -> API schemas, and the roll-up statistics."""
from __future__ import annotations

from collections import Counter

from models import ComplianceGapAssessment, ComplianceObligation
from schemas import GapAssessmentOut, GapStats
from services.gap_types import GapType


def to_out(g: ComplianceGapAssessment, o: ComplianceObligation) -> GapAssessmentOut:
    return GapAssessmentOut(
        id=g.id, obligation_id=g.obligation_id, mapping_id=g.mapping_id, gap_type=g.gap_type,
        additional_gaps=list(g.additional_gaps or []), risk_rating=g.risk_rating,
        risk_score=float(g.risk_score) if g.risk_score is not None else None,
        coverage_score=float(g.coverage_score), observation=g.observation or "", recommendation=g.recommendation or "",
        confidence_score=float(g.confidence_score or 0), owner_function=g.owner_function, needs_review=g.needs_review,
        stale=o.mapped_at != g.source_mapped_at, clause_ref=o.clause_ref, obligation_text=o.obligation_text,
        obligation_severity=o.severity, details=g.details or {}, assessed_at=g.updated_at or g.created_at,
    )


def build_stats(items: list[GapAssessmentOut]) -> GapStats:
    if not items:
        return GapStats()
    compliant = sum(1 for i in items if i.gap_type == GapType.NO_GAP)
    gaps = [i for i in items if i.gap_type != GapType.NO_GAP]
    return GapStats(
        total=len(items), compliant=compliant, with_gaps=len(gaps),
        by_risk=dict(Counter(i.risk_rating for i in items)),
        by_gap_type=dict(Counter(i.gap_type for i in gaps)),
        average_coverage=round(sum(i.coverage_score for i in items) / len(items), 1),
        needs_review=sum(1 for i in items if i.needs_review), stale=sum(1 for i in items if i.stale),
    )
