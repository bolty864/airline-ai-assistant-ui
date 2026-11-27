"""Agent 1 routes. Paths are unchanged from the original Agent 1 service, so the frontend keeps working."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import providers
from agents.pipeline import DocumentPipeline
from agents.regulatory_monitoring_agent import RegulatoryMonitoringAgent
from agents.watchdog import run_scan
from api.dependencies import get_monitoring_agent, get_pipeline_dep
from database import get_session
from repositories import AuditRepository, DocumentRepository, ObligationRepository
from schemas import (AuditLogList, AuditLogOut, CrawlResponse, CrawlTriggerRequest, DocumentList, DocumentObligations,
                     DocumentOut, HealthResponse, IngestRequest, IngestResponse, ObligationOut, ScanResult,
                     SimulateDeleteRequest)
from services.scrapers import CRAWLERS
from settings import Settings, get_settings

router = APIRouter(prefix="/api", tags=["Agent 1 - Regulatory Monitoring & Self-Healing"])
DEMO_SOURCES = Path(__file__).resolve().parents[1] / "sample_data" / "demo_sources"


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request, session: AsyncSession = Depends(get_session),
                       settings: Settings = Depends(get_settings)):
    db_ok = blob_ok = False
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    try:
        blob_ok = await providers.blob_service().healthy()
    except Exception:
        pass
    task = getattr(request.app.state, "watchdog_task", None)
    return HealthResponse(
        status="healthy" if db_ok and blob_ok else "degraded",
        database_connected=db_ok, blob_storage_connected=blob_ok,
        storage_mode="local" if settings.local_storage_root else "azure_blob",
        watchdog_active=bool(task and not task.done()),
        watchdog_interval_seconds=settings.watchdog_interval_seconds,
        llm_configured=bool(settings.azure_openai_endpoint and settings.azure_openai_key),
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/documents", response_model=DocumentList)
async def list_documents(regulator: str | None = Query(None), status: str | None = Query(None),
                         session: AsyncSession = Depends(get_session)):
    rows = await DocumentRepository(session).list_with_counts(regulator, status)
    docs = [DocumentOut.model_validate(r["doc"]).model_copy(update={"obligation_count": r["obligation_count"]})
            for r in rows]
    return DocumentList(total=len(docs), documents=docs)


@router.get("/documents/{doc_code}/obligations", response_model=DocumentObligations)
async def get_document_obligations(doc_code: str, session: AsyncSession = Depends(get_session)):
    doc = await DocumentRepository(session).get_by_doc_code(doc_code)
    if doc is None:
        raise HTTPException(404, f"Document '{doc_code}' not found")
    obs = await ObligationRepository(session).list_by_document(doc.id)
    return DocumentObligations(doc_code=doc.doc_code, status=doc.status, obligations_count=len(obs),
                               obligations=[ObligationOut.model_validate(o) for o in obs])


@router.get("/audit-logs", response_model=AuditLogList)
async def get_audit_logs(limit: int = Query(20, ge=1, le=200), doc_code: str | None = Query(None),
                         session: AsyncSession = Depends(get_session)):
    logs = await AuditRepository(session).list(limit, doc_code)
    return AuditLogList(logs=[AuditLogOut.model_validate(l) for l in logs])


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(payload: IngestRequest,
                          agent: RegulatoryMonitoringAgent = Depends(get_monitoring_agent),
                          pipeline: DocumentPipeline = Depends(get_pipeline_dep)):
    """Download, detect changes, store, then hand off to Agent 2 (extraction) and Agent 3 (mapping)."""
    result = await agent.ingest(payload)
    resp = IngestResponse(**result.model_dump(), message={
        "NEW_DOC": "New document registered", "DOC_UPDATED": "Document updated at source; new version stored",
        "DOC_UNCHANGED": "Document unchanged since last check"}[result.event])
    # Always hand off: Agent 2 skips unchanged files cheaply, but still runs if a previous extraction failed
    if payload.wait:
        resp.extraction = await pipeline.run(result.document_id, reason=result.event)
    else:
        pipeline.schedule(result.document_id, reason=result.event)
        resp.extraction_scheduled = True
    return resp


@router.post("/crawl/trigger", response_model=CrawlResponse)
async def trigger_crawl(payload: CrawlTriggerRequest,
                        agent: RegulatoryMonitoringAgent = Depends(get_monitoring_agent),
                        pipeline: DocumentPipeline = Depends(get_pipeline_dep)):
    targets = [r.upper() for r in payload.regulators]

    async def ingest_and_handoff(req: IngestRequest):
        res = await agent.ingest(req)
        pipeline.schedule(res.document_id, reason=f"crawl:{res.event}")
        return res

    results: dict[str, list[dict]] = {}
    for reg in targets:
        if reg in CRAWLERS:
            results[reg] = await CRAWLERS[reg](providers.source_fetcher(), ingest_and_handoff, payload.max_items)
    processed = sum(1 for items in results.values() for i in items if i.get("event") not in {None, "FAILED"})
    return CrawlResponse(message="Regulatory crawl completed", targets=targets,
                         not_supported=[t for t in targets if t not in CRAWLERS],
                         total_processed=processed, ingested_documents=results)


@router.post("/watchdog/scan", response_model=ScanResult)
async def force_watchdog_scan():
    """Run one integrity scan now (the background watchdog runs every WATCHDOG_INTERVAL_SECONDS)."""
    return await run_scan()


# ------------------------------------------------------------------ demo helpers

@router.post("/demo/simulate-delete")
async def simulate_blob_deletion(payload: SimulateDeleteRequest,
                                 agent: RegulatoryMonitoringAgent = Depends(get_monitoring_agent),
                                 settings: Settings = Depends(get_settings)):
    if not settings.demo_endpoints_enabled:
        raise HTTPException(404, "Demo endpoints are disabled")
    return await agent.simulate_delete(payload.doc_code)


@router.get("/demo/sources/{filename}", include_in_schema=False)
async def demo_source(filename: str, settings: Settings = Depends(get_settings)):
    """Offline stand-in for a regulator website, so the self-healing demo works without internet."""
    path = (DEMO_SOURCES / filename).resolve()
    if not settings.demo_endpoints_enabled or DEMO_SOURCES.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path)
