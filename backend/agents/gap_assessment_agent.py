"""Agent 4: Compliance Gap Assessment Agent.

Workflow
  1. read the document and its obligations (Agent 2) and Agent 3's mappings (policies, controls, systems)
  2. skip obligations Agent 3 has not finished; skip ones whose inputs are unchanged since the last run
  3. per obligation: rules check the controls, GPT-4o compares parameters, rules score coverage and risk
  4. upsert one assessment per obligation (compliance_gap_assessments), audit log, return summary
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agents.errors import DocumentNotFoundError, DocumentNotReadyError, EnterpriseRepositoryEmptyError
from models import ComplianceObligation
from repositories import AuditRepository, DocumentRepository, GapRepository, MappingRepository, ObligationRepository
from schemas import FailedObligation, GapAnalysisSummary, GapReport, GapUsageOut
from services.gap_analyzer import GapAnalyzer, GapLLMError
from services.gap_presenter import build_stats, to_out
from services.gap_types import Finding, ObligationView
from settings import Settings

log = logging.getLogger(__name__)

NOT_READY_STATUSES = {"MISSING", "HEALING"}
MAPPING_DONE = {"MAPPED", "NEEDS_REVIEW", "UNMAPPED"}     # Agent 3 finished (UNMAPPED = it found nothing)


class GapAssessmentAgent:
    def __init__(self, session: AsyncSession, documents: DocumentRepository, obligations: ObligationRepository,
                 mappings: MappingRepository, gaps: GapRepository, audit: AuditRepository,
                 analyzer: GapAnalyzer, settings: Settings):
        self.session = session
        self.documents = documents
        self.obligations = obligations
        self.mappings = mappings
        self.gaps = gaps
        self.audit = audit
        self.analyzer = analyzer
        self.settings = settings

    async def run(self, document_id: int, force: bool = False) -> GapAnalysisSummary:
        started = time.perf_counter()
        doc = await self.documents.get_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundError(f"Regulatory document {document_id} not found")
        if (doc.status or "").upper() in NOT_READY_STATUSES:
            raise DocumentNotReadyError(f"Document {doc.doc_code} is {doc.status}; wait for Agent 1 to restore it")
        controls, _policies = await self.mappings.enterprise_stats()
        if controls == 0:
            raise EnterpriseRepositoryEmptyError(
                "No controls are registered. Run POST /api/mapping/ingest first, otherwise every "
                "obligation would be reported as a Missing Control.")

        summary = GapAnalysisSummary(document_id=doc.id, doc_code=doc.doc_code, status="COMPLETED")
        obligations = list(await self.obligations.list_for_assessment(document_id))
        summary.total_obligations = len(obligations)
        if not obligations:
            summary.status = "NO_OBLIGATIONS"
            summary.warnings.append("No obligations extracted yet; run Agent 2 first.")
            return await self._finish(summary, started, document_id)

        await self.audit.log("GAP_ASSESSMENT_STARTED", doc.doc_code, {"document_id": doc.id, "force": force})
        ready = [o for o in obligations if o.mapping_status in MAPPING_DONE]
        summary.pending_mapping = [o.id for o in obligations if o.mapping_status not in MAPPING_DONE]
        assets = await self.mappings.load_for_obligations([o.id for o in ready])
        known = await self.gaps.fingerprints([o.id for o in ready])
        await self.session.commit()           # release the connection while GPT works

        now = datetime.now(UTC).replace(tzinfo=None)     # DB timestamps are naive UTC
        todo = []
        for o in ready:
            prep = self.analyzer.prepare(self._view(o, doc), assets.get(o.id, []), now)
            if not force and known.get(o.id) == prep.fingerprint:
                summary.unchanged += 1
            else:
                todo.append(prep)

        sem = asyncio.Semaphore(self.settings.gap_concurrency)

        async def one(prep) -> Finding | FailedObligation:
            async with sem:
                try:
                    return await self.analyzer.assess(prep)
                except GapLLMError as exc:
                    return FailedObligation(obligation_id=prep.ob.id, error=str(exc))
                except Exception as exc:       # one bad obligation must not sink the document
                    log.exception("Gap assessment failed", extra={"obligation_id": prep.ob.id})
                    return FailedObligation(obligation_id=prep.ob.id, error=f"unexpected: {exc}"[:300])

        results = await asyncio.gather(*(one(p) for p in todo))
        findings = [r for r in results if isinstance(r, Finding)]
        summary.failed = [r for r in results if isinstance(r, FailedObligation)]
        summary.assessed = len(findings)
        summary.llm_assessed = sum(1 for f in findings if f.llm_calls)
        if findings:
            summary.usage = GapUsageOut(model=self.analyzer.deployment, llm_calls=sum(f.llm_calls for f in findings),
                                        prompt_tokens=sum(f.prompt_tokens for f in findings),
                                        completion_tokens=sum(f.completion_tokens for f in findings))
        await self._persist(document_id, findings)

        if summary.failed or summary.pending_mapping:
            summary.status = "PARTIAL"
        if not todo and not summary.failed and not summary.pending_mapping:
            summary.status = "SKIPPED_UNCHANGED"
        elif not ready and not summary.failed:
            summary.status = "PENDING_MAPPING"
        if summary.pending_mapping:
            summary.warnings.append(f"{len(summary.pending_mapping)} obligation(s) are still being mapped by Agent 3.")
        await self.audit.log("GAP_ASSESSMENT_COMPLETED", doc.doc_code, {
            "document_id": doc.id, "status": summary.status, "assessed": summary.assessed,
            "unchanged": summary.unchanged, "failed": len(summary.failed)})
        return await self._finish(summary, started, document_id)

    async def report(self, document_id: int, risk_rating: str | None = None, gap_type: str | None = None) -> GapReport:
        doc = await self.documents.get_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundError(f"Regulatory document {document_id} not found")
        rows = await self.gaps.list_for_document(document_id, risk_rating, gap_type)
        items = [to_out(g, o) for g, o in rows]
        return GapReport(document_id=doc.id, doc_code=doc.doc_code, stats=build_stats(items), assessments=items)

    # ------------------------------------------------------------------ helpers
    async def _persist(self, document_id: int, findings: list[Finding]) -> None:
        await self.gaps.lock_document(document_id)
        alive = await self.obligations.existing_ids([f.obligation_id for f in findings])   # re-extraction may have replaced them
        rows = [{
            "obligation_id": f.obligation_id, "mapping_id": f.mapping_id, "gap_type": f.gap_type,
            "risk_rating": f.risk_rating, "coverage_score": f.coverage, "observation": f.observation,
            "recommendation": f.recommendation, "confidence_score": f.confidence, "risk_score": f.risk_score,
            "owner_function": f.owner_function, "additional_gaps": f.additional_gaps, "needs_review": f.needs_review,
            "details": f.details, "input_fingerprint": f.fingerprint, "source_mapped_at": f.source_mapped_at,
            "model_used": f.model_used,
        } for f in findings if f.obligation_id in alive]
        await self.gaps.upsert_many(rows)
        await self.session.commit()

    async def _finish(self, summary: GapAnalysisSummary, started: float, document_id: int) -> GapAnalysisSummary:
        rows = await self.gaps.list_for_document(document_id)
        summary.assessments = [to_out(g, o) for g, o in rows]
        summary.stats = build_stats(summary.assessments)
        summary.duration_ms = int((time.perf_counter() - started) * 1000)
        await self.session.commit()
        log.info("Gap assessment finished", extra={"document_id": document_id, "status": summary.status,
                                                   "assessed": summary.assessed, "unchanged": summary.unchanged})
        return summary

    @staticmethod
    def _view(o: ComplianceObligation, doc) -> ObligationView:
        return ObligationView(
            id=o.id, text=o.obligation_text, regulator=doc.regulator or "", document_title=doc.title or doc.doc_code,
            clause_ref=o.clause_ref, citation=o.citation, obligation_type=o.obligation_type, severity=o.severity,
            owner_function=o.owner_function, target_system=getattr(o, "target_system", None),
            confidence=float(o.confidence_score) if o.confidence_score is not None else None,
            mapping_status=o.mapping_status, mapped_at=o.mapped_at,
        )
