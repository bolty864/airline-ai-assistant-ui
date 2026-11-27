"""AeroComply AI backend.

Agent 1  Regulatory Monitoring & Self-Healing   /api/ingest, /api/documents, /api/watchdog, /api/crawl ...
Agent 2  Obligation Extraction                  /api/obligations/...
Agent 3  Policy & Control Mapping               /api/mapping/...
Agent 4  Compliance Gap Assessment              /api/gaps/...
Agent 5  Regulatory Change Impact & Remediation /api/impact-analysis/..., /api/remediation-tasks/...
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import providers
from agents.errors import (DocumentNotFoundError, DocumentNotReadyError, EnterpriseRepositoryEmptyError,
                           InvalidComparisonError)
from agents.obligation_extraction_agent import ExtractionError
from agents.pipeline import get_pipeline
from agents.policy_mapping.api import router as mapping_router
from agents.regulatory_monitoring_agent import DocumentNotRegisteredError
from agents.watchdog import watchdog_loop
from api.gap_routes import router as gap_router
from api.impact_routes import router as impact_router
from api.monitoring_routes import router as monitoring_router
from api.obligation_routes import router as obligation_router
from database import dispose_engine
from logging_config import setup_logging
from services.blob_storage import BlobNotFoundError
from services.document_types import DocumentParseError
from services.openai_client import OpenAIConfigError
from services.source_fetcher import SourceFetchError, SourceNotAllowedError
from settings import get_settings

settings = get_settings()
setup_logging(settings.log_level, settings.log_json)
log = logging.getLogger("aerocomply")


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks: list[asyncio.Task] = []
    # Agent 3 worker -> Agent 4: assess documents the worker has just mapped
    providers.agent3_service().on_documents_mapped = get_pipeline().on_documents_mapped
    if settings.watchdog_enabled:
        app.state.watchdog_task = asyncio.create_task(watchdog_loop())
        tasks.append(app.state.watchdog_task)
    if settings.agent3_worker_enabled:
        # Safety net: maps any PENDING obligation that the direct hand-off missed
        tasks.append(asyncio.create_task(providers.agent3_service().worker(settings.agent3_poll_seconds)))
    log.info("Backend started", extra={"watchdog": settings.watchdog_enabled,
                                       "agent3_worker": settings.agent3_worker_enabled})
    yield
    for t in tasks:
        t.cancel()
    for t in tasks:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(get_pipeline().drain(), timeout=30)
    await dispose_engine()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=settings.cors_origins.strip() != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(monitoring_router)
app.include_router(obligation_router)
app.include_router(mapping_router)
app.include_router(gap_router)
app.include_router(impact_router)


def _error(status: int, code: str, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "detail": str(exc)})


_ERRORS: list[tuple[type[Exception], int, str]] = [
    (DocumentNotFoundError, 404, "document_not_found"),
    (DocumentNotRegisteredError, 404, "document_not_found"),
    (BlobNotFoundError, 404, "file_not_found"),
    (DocumentNotReadyError, 409, "document_not_ready"),
    (EnterpriseRepositoryEmptyError, 409, "enterprise_repository_empty"),
    (InvalidComparisonError, 422, "invalid_comparison"),
    (SourceNotAllowedError, 400, "source_not_allowed"),
    (SourceFetchError, 502, "source_unreachable"),
    (DocumentParseError, 422, "document_unreadable"),
    (OpenAIConfigError, 503, "llm_not_configured"),
]
for _exc, _status, _code in _ERRORS:
    app.add_exception_handler(_exc, lambda req, exc, s=_status, c=_code: _error(s, c, exc))


@app.exception_handler(ExtractionError)
async def _extraction(_: Request, exc: ExtractionError):
    cause = exc.__cause__
    for exc_type, status, code in _ERRORS:
        if isinstance(cause, exc_type):
            return _error(status, code, cause)
    return _error(502, "extraction_failed", exc)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "app": settings.app_name}
