from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from agents.gap_assessment_agent import GapAssessmentAgent
from agents.pipeline import DocumentPipeline
from api.dependencies import get_gap_agent, get_pipeline_dep
from schemas import GapAnalysisAccepted, GapAnalysisSummary, GapReport
from settings import Settings, get_settings

router = APIRouter(prefix="/api/gaps", tags=["Agent 4 - Compliance Gap Assessment"])

RISKS = "CRITICAL|HIGH|MEDIUM|LOW"


@router.post(
    "/analyze/{document_id}",
    response_model=GapAnalysisSummary | GapAnalysisAccepted,
    responses={202: {"model": GapAnalysisAccepted}, 404: {}, 409: {}, 502: {}},
)
async def analyze_gaps(
    document_id: int,
    force: bool = Query(False, description="Re-assess even if nothing changed since the last run"),
    run_in_background: bool = Query(False, description="Return 202 immediately (large documents)"),
    agent: GapAssessmentAgent = Depends(get_gap_agent),
    pipeline: DocumentPipeline = Depends(get_pipeline_dep),
    settings: Settings = Depends(get_settings),
):
    """Assess how well existing policies and controls cover each obligation of a regulatory document.

    Obligations Agent 3 has not finished mapping are skipped and listed in `pending_mapping`.
    """
    if run_in_background:
        pipeline.schedule_assess(document_id, force=force, reason="api")
        body = GapAnalysisAccepted(document_id=document_id, message="Gap assessment started; poll GET /api/gaps/{id}")
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body.model_dump())
    summary = await agent.run(document_id, force=force)
    if settings.auto_impact_after_assessment:
        pipeline.schedule_impact(document_id, reason="after_assessment")
    return summary


@router.get("/{document_id}", response_model=GapReport, responses={404: {}})
async def get_gaps(
    document_id: int,
    risk_rating: str | None = Query(None, pattern=f"^({RISKS})$", description="Filter by rating"),
    gap_type: str | None = Query(None, description="Filter by gap type, e.g. 'Missing Control'"),
    agent: GapAssessmentAgent = Depends(get_gap_agent),
):
    """Stored assessments, highest risk first, with roll-up statistics."""
    return await agent.report(document_id, risk_rating=risk_rating, gap_type=gap_type)
