"""Agent 2 -> Agent 3 -> Agent 4 for one document. Used by Agent 1 (new / updated / healed docs) and the APIs.

Background runs are de-duplicated per document: if a document is already being processed, a new
request is folded into one follow-up run instead of running twice in parallel.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import lru_cache

from sqlalchemy import select

import providers
from agents.errors import (DocumentNotFoundError, DocumentNotReadyError, EnterpriseRepositoryEmptyError,
                           InvalidComparisonError)
from database import get_sessionmaker
from models import RegulatoryDocument
from schemas import ExtractionSummary, GapAnalysisSummary, ImpactAnalysisSummary
from settings import get_settings

log = logging.getLogger(__name__)

# Expected, non-fatal reasons for a background assessment to stop (logged as warnings, no traceback)
_BENIGN = (DocumentNotFoundError, DocumentNotReadyError, EnterpriseRepositoryEmptyError, InvalidComparisonError)


class _KeyedRunner:
    """At most one running task per key; requests that arrive meanwhile are folded into one re-run."""

    def __init__(self, fn: Callable[[int, bool, str], Awaitable], label: str):
        self.fn, self.label = fn, label
        self.tasks: dict[int, asyncio.Task] = {}
        self.pending: dict[int, bool] = {}           # key -> force

    def schedule(self, key: int, force: bool = False, reason: str = "api") -> None:
        if key in self.tasks:
            self.pending[key] = self.pending.get(key, False) or force
            return
        self.tasks[key] = asyncio.create_task(self._guarded(key, force, reason))

    async def _guarded(self, key: int, force: bool, reason: str) -> None:
        try:
            await self.fn(key, force, reason)
        except _BENIGN as exc:
            log.warning("%s skipped: %s", self.label, exc, extra={"document_id": key, "reason": reason})
        except Exception:
            log.exception("Background %s failed", self.label, extra={"document_id": key, "reason": reason})
        finally:
            self.tasks.pop(key, None)
            if key in self.pending:
                self.schedule(key, self.pending.pop(key), reason="rerun")

    def is_running(self, key: int) -> bool:
        return key in self.tasks


class DocumentPipeline:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._sem = asyncio.Semaphore(self.settings.pipeline_concurrency)
        self._assess_sem = asyncio.Semaphore(max(1, self.settings.pipeline_concurrency))
        self._extract = _KeyedRunner(self._run_quiet, "pipeline")
        self._assess = _KeyedRunner(self._assess_quiet, "gap assessment")
        self._impact_sem = asyncio.Semaphore(max(1, self.settings.pipeline_concurrency))
        self._impact = _KeyedRunner(self._impact_quiet, "impact analysis")

    # ------------------------------------------------------------ Agent 2 -> 3 -> (4)
    async def run(self, document_id: int, force: bool = False, reason: str = "api") -> ExtractionSummary:
        from agents.factory import build_extraction_agent

        async with self._sem:
            async with get_sessionmaker()() as session:
                summary = await build_extraction_agent(session, self.settings).run(document_id, force=force)
            if (self.settings.auto_map_after_extraction and summary.obligations_extracted
                    and summary.status != "SKIPPED_UNCHANGED"):
                try:
                    await providers.agent3_service().map_document(summary.doc_code)
                    summary.mapping_queued = True
                    if self.settings.auto_assess_after_mapping:
                        self.schedule_assess(document_id, reason="after_mapping")
                except Exception:
                    log.exception("Agent 3 mapping failed; the worker retries PENDING rows",
                                  extra={"doc_code": summary.doc_code})
            log.info("Pipeline finished", extra={"document_id": document_id, "reason": reason,
                                                 "status": summary.status, "obligations": summary.obligations_extracted})
            return summary

    async def _run_quiet(self, document_id: int, force: bool, reason: str) -> None:
        await self.run(document_id, force, reason)

    def schedule(self, document_id: int, force: bool = False, reason: str = "api") -> None:
        self._extract.schedule(document_id, force, reason)

    # ------------------------------------------------------------ Agent 4
    async def assess(self, document_id: int, force: bool = False, reason: str = "api") -> GapAnalysisSummary:
        from agents.factory import build_gap_agent

        async with self._assess_sem:
            async with get_sessionmaker()() as session:
                summary = await build_gap_agent(session, self.settings).run(document_id, force=force)
        log.info("Gap assessment pipeline finished", extra={"document_id": document_id, "reason": reason,
                                                            "status": summary.status})
        if self.settings.auto_impact_after_assessment:
            self.schedule_impact(document_id, reason="after_assessment")
        return summary

    async def _assess_quiet(self, document_id: int, force: bool, reason: str) -> None:
        await self.assess(document_id, force, reason)

    def schedule_assess(self, document_id: int, force: bool = False, reason: str = "api") -> None:
        self._assess.schedule(document_id, force, reason)

    # ------------------------------------------------------------ Agent 5
    async def impact(self, document_id: int, force: bool = False, reason: str = "api") -> ImpactAnalysisSummary:
        from agents.factory import build_impact_agent

        async with self._impact_sem:
            async with get_sessionmaker()() as session:
                summary = await build_impact_agent(session, self.settings).run(document_id, force=force)
        log.info("Impact analysis pipeline finished", extra={"document_id": document_id, "reason": reason,
                                                             "status": summary.status})
        return summary

    async def _impact_quiet(self, document_id: int, force: bool, reason: str) -> None:
        await self.impact(document_id, force, reason)

    def schedule_impact(self, document_id: int, force: bool = False, reason: str = "api") -> None:
        self._impact.schedule(document_id, force, reason)

    async def on_documents_mapped(self, doc_codes: list[str]) -> None:
        """Hook for the Agent 3 worker: documents whose PENDING obligations were just mapped get assessed."""
        if not (self.settings.auto_assess_after_mapping and doc_codes):
            return
        async with get_sessionmaker()() as session:
            ids = (await session.execute(
                select(RegulatoryDocument.id).where(RegulatoryDocument.doc_code.in_(doc_codes)))).scalars().all()
        for doc_id in ids:
            self.schedule_assess(doc_id, reason="worker_mapped")

    # ------------------------------------------------------------ lifecycle
    async def drain(self) -> None:
        """Wait for all background runs (tests, graceful shutdown). Extraction can schedule assessment, so loop."""
        while self._extract.tasks or self._assess.tasks or self._impact.tasks:
            await asyncio.gather(*list(self._extract.tasks.values()), *list(self._assess.tasks.values()),
                                 *list(self._impact.tasks.values()), return_exceptions=True)
            await asyncio.sleep(0)

    def is_running(self, document_id: int) -> bool:
        return self._extract.is_running(document_id)

    def is_assessing(self, document_id: int) -> bool:
        return self._assess.is_running(document_id)

    def is_analysing_impact(self, document_id: int) -> bool:
        return self._impact.is_running(document_id)


@lru_cache
def get_pipeline() -> DocumentPipeline:
    return DocumentPipeline()
