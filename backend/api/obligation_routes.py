from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agents.obligation_extraction_agent import ObligationExtractionAgent
from agents.pipeline import DocumentPipeline
from api.dependencies import get_agent3_service, get_extraction_agent, get_pipeline_dep
from database import get_session
from repositories import ObligationRepository
from schemas import ExtractionAccepted, ExtractionSummary, ObligationOut
from settings import Settings, get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/obligations", tags=["Agent 2 - Obligation Extraction"])


async def _map_after_extraction(agent3, pipeline: DocumentPipeline, document_id: int, doc_code: str,
                                assess: bool) -> None:
    try:
        res = await agent3.map_document(doc_code)
        log.info("Agent 3 mapping finished", extra={"doc_code": doc_code, "processed": res.get("processed")})
        if assess:
            pipeline.schedule_assess(document_id, reason="after_mapping")
    except Exception:
        log.exception("Agent 3 mapping failed; the worker will retry PENDING obligations", extra={"doc_code": doc_code})


@router.post(
    "/extract/{document_id}",
    response_model=ExtractionSummary | ExtractionAccepted,
    responses={202: {"model": ExtractionAccepted}, 404: {}, 409: {}, 422: {}, 502: {}},
)
async def extract_obligations(
    document_id: int,
    background_tasks: BackgroundTasks,
    force: bool = Query(False, description="Re-extract even if the file is unchanged since the last run"),
    run_in_background: bool = Query(False, description="Return 202 immediately (large documents)"),
    agent: ObligationExtractionAgent = Depends(get_extraction_agent),
    agent3=Depends(get_agent3_service),
    pipeline: DocumentPipeline = Depends(get_pipeline_dep),
    settings: Settings = Depends(get_settings),
):
    """Extract mandatory obligations from a regulatory document registered by Agent 1."""
    if run_in_background:
        pipeline.schedule(document_id, force=force, reason="api")
        body = ExtractionAccepted(document_id=document_id, message="Extraction started; see /api/audit-logs")
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body.model_dump())

    summary = await agent.run(document_id, force=force)
    if settings.auto_map_after_extraction and summary.obligations_extracted and summary.status != "SKIPPED_UNCHANGED":
        background_tasks.add_task(_map_after_extraction, agent3, pipeline, summary.document_id, summary.doc_code,
                                  settings.auto_assess_after_mapping)
        summary.mapping_queued = True
    return summary


@router.get("/document/{document_id}", response_model=list[ObligationOut])
async def list_obligations(document_id: int, session: AsyncSession = Depends(get_session)):
    rows = await ObligationRepository(session).list_by_document(document_id)
    return [ObligationOut.model_validate(r) for r in rows]
