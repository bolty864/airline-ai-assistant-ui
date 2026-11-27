from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from agents.errors import InvalidComparisonError
from agents.impact_assessment_agent import ImpactAssessmentAgent
from agents.pipeline import DocumentPipeline
from api.dependencies import get_impact_agent, get_pipeline_dep
from schemas import ImpactAccepted, ImpactAnalysisSummary, ImpactReport, TaskReport

router = APIRouter(tags=["Agent 5 - Regulatory Change Impact & Remediation"])

RISKS = "CRITICAL|HIGH|MEDIUM|LOW"
CHANGE_TYPES = ("NEW_OBLIGATION|MODIFIED_OBLIGATION|REMOVED_OBLIGATION|SEVERITY_CHANGE|RETENTION_CHANGE|"
                "REPORTING_CHANGE|SECURITY_REQUIREMENT_CHANGE")


@router.post(
    "/api/impact-analysis/{document_id}",
    response_model=ImpactAnalysisSummary | ImpactAccepted,
    responses={202: {"model": ImpactAccepted}, 404: {}, 409: {}, 422: {}, 502: {}},
)
async def analyze_impact(
    document_id: int,
    force: bool = Query(False, description="Re-analyse every change even if nothing changed since the last run"),
    run_in_background: bool = Query(False, description="Return 202 immediately (large documents)"),
    compare_to_document_id: int | None = Query(
        None, description="Compare against another document's current obligations instead of this document's previous version"),
    agent: ImpactAssessmentAgent = Depends(get_impact_agent),
    pipeline: DocumentPipeline = Depends(get_pipeline_dep),
):
    """Compare the new regulation with the previous one and work out what it means for controls, systems and teams.

    By default the previous version is the one Agent 2 saved when it last replaced this document's obligations.
    """
    if run_in_background:
        if compare_to_document_id is not None:
            raise InvalidComparisonError("compare_to_document_id needs a synchronous run (run_in_background=false)")
        pipeline.schedule_impact(document_id, force=force, reason="api")
        body = ImpactAccepted(document_id=document_id,
                              message="Impact analysis started; poll GET /api/impact-analysis/{document_id}")
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body.model_dump())
    return await agent.run(document_id, force=force, compare_to_document_id=compare_to_document_id)


@router.get("/api/impact-analysis/{document_id}", response_model=ImpactReport, responses={404: {}})
async def get_impact_analysis(
    document_id: int,
    risk_rating: str | None = Query(None, pattern=f"^({RISKS})$", description="Filter by rating"),
    change_type: str | None = Query(None, pattern=f"^({CHANGE_TYPES})$", description="Filter by change type"),
    agent: ImpactAssessmentAgent = Depends(get_impact_agent),
):
    """Stored result of the last analysis: overall risk, every change (highest risk first) and its remediation tasks."""
    return await agent.report(document_id, risk_rating=risk_rating, change_type=change_type)


@router.get("/api/remediation-tasks/{document_id}", response_model=TaskReport, responses={404: {}})
async def get_remediation_tasks(
    document_id: int,
    status_: str | None = Query(None, alias="status", pattern="^(OPEN|IN_PROGRESS|DONE|CANCELLED)$"),
    priority: str | None = Query(None, pattern=f"^({RISKS})$"),
    owner_team: str | None = Query(None, description="Exact team name, case-insensitive"),
    agent: ImpactAssessmentAgent = Depends(get_impact_agent),
):
    """Remediation backlog of a regulation, most urgent first."""
    return await agent.tasks(document_id, status=status_, priority=priority, owner_team=owner_team)
