"""Agent 2: Obligation Extraction Agent.

Workflow
  1. read document metadata (regulatory_documents)      6. keep mandatory obligations only, apply rules
  2. download file from blob_path                       7. embed (text-embedding-3-small, shared cache)
  3. extract text (PDF / DOCX / HTML)                   8. replace obligations of the document
  4. split into clauses                                 9. audit log
  5. GPT-4o per clause, but only for clauses with      10. return summary; Agent 3 picks up PENDING rows
     mandatory language (cuts LLM calls a lot)
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from agents.errors import DocumentNotFoundError, DocumentNotReadyError  # noqa: F401  (re-exported)
from models import ComplianceObligation, RegulatoryDocument
from repositories import AuditRepository, DocumentRepository, ObligationRepository
from schemas import ExtractionSummary, FailedClause, ObligationOut, UsageOut
from services.blob_storage import BlobStorageService
from services.clause_splitter import Clause, ClauseSplitter
from services.embedding_service import EmbeddingService
from services.llm_extractor import ClauseExtraction, DocumentContext, ExtractedObligation, LLMExtractor
from services.obligation_rules import has_mandatory_language, normalize_type, owner_for, severity_for
from services.parser_factory import ParserFactory
from services.text_utils import loose, sentences, sha256_bytes
from settings import Settings

log = logging.getLogger(__name__)

NOT_READY_STATUSES = {"MISSING", "HEALING"}
MAX_FAILED_CLAUSE_RATIO = 0.2   # above this, abort and keep the previous obligations untouched


class ExtractionError(Exception):
    pass


class ObligationExtractionAgent:
    def __init__(
        self,
        session: AsyncSession,
        documents: DocumentRepository,
        obligations: ObligationRepository,
        audit: AuditRepository,
        blob: BlobStorageService,
        parsers: ParserFactory,
        splitter: ClauseSplitter,
        extractor: LLMExtractor,
        embedder: EmbeddingService,
        settings: Settings,
    ):
        self.session = session
        self.documents = documents
        self.obligations = obligations
        self.audit = audit
        self.blob = blob
        self.parsers = parsers
        self.splitter = splitter
        self.extractor = extractor
        self.embedder = embedder
        self.settings = settings

    async def run(self, document_id: int, force: bool = False) -> ExtractionSummary:
        started = time.perf_counter()
        doc = await self.documents.get_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundError(f"Regulatory document {document_id} not found")
        if (doc.status or "").upper() in NOT_READY_STATUSES:
            raise DocumentNotReadyError(f"Document {doc.doc_code} is {doc.status}; wait for Agent 1 to restore it")

        ctx_log = {"doc_code": doc.doc_code, "document_id": doc.id}
        log.info("Extraction started", extra=ctx_log)
        await self.audit.log("EXTRACTION_STARTED", doc.doc_code, {"document_id": doc.id, "force": force})
        await self.session.commit()

        try:
            return await self._run(doc, force, started, ctx_log)
        except (DocumentNotFoundError, DocumentNotReadyError):
            raise
        except Exception as exc:
            await self.session.rollback()  # expires ORM objects, so only use the captured ids below
            log.exception("Extraction failed", extra=ctx_log)
            await self.audit.log("EXTRACTION_FAILED", ctx_log["doc_code"],
                                 {"document_id": ctx_log["document_id"], "error": str(exc)[:1000]})
            await self.session.commit()
            if isinstance(exc, ExtractionError):
                raise
            raise ExtractionError(str(exc)) from exc

    # ------------------------------------------------------------------ pipeline

    async def _run(self, doc: RegulatoryDocument, force: bool, started: float, ctx_log: dict) -> ExtractionSummary:
        # 2. read file
        data = await self.blob.download(doc.blob_path)
        file_hash = sha256_bytes(data)
        hash_ok = file_hash == doc.sha256_hash
        if not hash_ok:
            log.warning("File hash differs from registry", extra={**ctx_log, "file_sha256": file_hash})
            await self.audit.log("DOC_HASH_MISMATCH", doc.doc_code,
                                 {"registry_sha256": doc.sha256_hash, "file_sha256": file_hash})

        existing = await self.obligations.count_by_document(doc.id)
        if not force and existing and await self._already_extracted(doc.doc_code, file_hash):
            current = await self.obligations.list_by_document(doc.id)
            await self.session.commit()
            return ExtractionSummary(
                document_id=doc.id, doc_code=doc.doc_code, regulator=doc.regulator, status="SKIPPED_UNCHANGED",
                file_sha256=file_hash, hash_matches_registry=hash_ok, obligations_extracted=len(current),
                duration_ms=self._ms(started), obligations=[self._out(o) for o in current],
                warnings=["Document unchanged since last extraction; use force=true to re-run"],
            )

        # 3-4. parse + split (CPU bound -> thread)
        parsed = await asyncio.to_thread(self.parsers.parse, doc.filename or doc.blob_path, data)
        clauses = await asyncio.to_thread(self.splitter.split, parsed.text)
        candidates = [c for c in clauses if c.is_candidate]
        log.info("Clauses split", extra={**ctx_log, "clauses": len(clauses), "candidates": len(candidates)})

        # 5. LLM per candidate clause, bounded concurrency
        ctx = DocumentContext(regulator=doc.regulator, title=doc.title, doc_code=doc.doc_code)
        sem = asyncio.Semaphore(self.settings.extraction_concurrency)

        async def run_one(clause: Clause) -> ClauseExtraction:
            async with sem:
                return await self.extractor.extract(clause, ctx)

        results = await asyncio.gather(*(run_one(c) for c in candidates))
        failed = [FailedClause(clause_number=r.clause.clause_number, error=r.error) for r in results if r.error]
        if candidates and len(failed) / len(candidates) > MAX_FAILED_CLAUSE_RATIO:
            raise ExtractionError(
                f"{len(failed)}/{len(candidates)} clauses failed; previous obligations kept. First error: {failed[0].error}"
            )

        # 6. post-process
        rows, stats = self._build_rows(doc, results)

        # 7. embeddings (one batched call, cached)
        if rows:
            vectors = await self.embedder.embed_many([r.obligation_text for r in rows])
            for row, vec in zip(rows, vectors):
                row.embedding = vec

        # 8-9. replace atomically
        await self.obligations.snapshot_by_document(doc.id, doc.sha256_hash, doc.version_tag,
                                                    keep=self.settings.obligation_versions_keep)   # Agent 5: previous version
        removed = await self.obligations.delete_by_document(doc.id)
        await self.obligations.bulk_create(rows)
        usage = UsageOut(
            model=self.extractor.deployment,
            llm_calls=len(results),
            prompt_tokens=sum(r.prompt_tokens for r in results),
            completion_tokens=sum(r.completion_tokens for r in results),
            embedding_model=self.embedder.deployment,
            embedding_tokens=self.embedder.tokens_used,
            embedding_cache_hits=self.embedder.cache_hits,
        )
        by_type = Counter(r.obligation_type for r in rows)
        by_sev = Counter(r.severity for r in rows)
        status = "PARTIAL" if failed else ("COMPLETED" if rows else "NO_OBLIGATIONS")
        details = {
            "document_id": doc.id, "sha256": file_hash, "status": status, "format": parsed.format,
            "clauses": len(clauses), "candidate_clauses": len(candidates), "obligations": len(rows),
            "replaced": removed, "failed_clauses": [f.model_dump() for f in failed],
            "by_type": dict(by_type), "by_severity": dict(by_sev), "usage": usage.model_dump(), **stats,
        }
        await self.audit.log("OBLIGATIONS_EXTRACTED", doc.doc_code, details)
        if removed:
            await self.audit.log("OBLIGATIONS_REPROCESSED", doc.doc_code,
                                 {"document_id": doc.id, "replaced": removed, "new": len(rows)})
        await self.session.commit()
        log.info("Extraction finished", extra={**ctx_log, "obligations": len(rows), "status": status})

        return ExtractionSummary(
            document_id=doc.id, doc_code=doc.doc_code, regulator=doc.regulator, status=status,
            reprocessed=bool(removed), file_sha256=file_hash, hash_matches_registry=hash_ok,
            format=parsed.format, page_count=parsed.page_count, total_clauses=len(clauses),
            candidate_clauses=len(candidates), skipped_non_mandatory=len(clauses) - len(candidates),
            failed_clauses=failed, obligations_extracted=len(rows), by_type=dict(by_type), by_severity=dict(by_sev),
            usage=usage, duration_ms=self._ms(started), warnings=parsed.warnings,
            obligations=[self._out(r) for r in rows], **stats,
        )

    # ------------------------------------------------------------------ rules & validation

    def _build_rows(self, doc: RegulatoryDocument, results: list[ClauseExtraction]):
        rows: list[ComplianceObligation] = []
        seen: set[str] = set()
        stats = {"dropped_low_confidence": 0, "duplicates_removed": 0, "citations_repaired": 0}
        min_conf = self.settings.extraction_min_confidence

        for res in results:
            for ob in res.obligations:
                if not ob.requirement:
                    continue
                conf = min(max(ob.confidence_score, 0.0), 1.0)
                if conf < min_conf:
                    stats["dropped_low_confidence"] += 1
                    continue
                citation, repaired = self._verified_citation(ob, res.clause.text)
                stats["citations_repaired"] += int(repaired)
                if not has_mandatory_language(citation) and not has_mandatory_language(ob.requirement):
                    stats["dropped_low_confidence"] += 1  # no mandatory wording anywhere: not an obligation
                    continue
                key = loose(ob.requirement)
                if key in seen:
                    stats["duplicates_removed"] += 1
                    continue
                seen.add(key)

                ob_type = normalize_type(ob.obligation_type)
                rows.append(ComplianceObligation(
                    document_id=doc.id,
                    clause_ref=self._clause_ref(ob, res.clause),
                    obligation_text=ob.requirement,
                    obligation_type=ob_type,
                    owner_function=owner_for(ob_type),                 # rule, not GPT
                    severity=severity_for(citation),                    # rule, not GPT
                    citation=citation,
                    confidence_score=Decimal(str(round(conf * 100, 2))),
                    target_system=ob.target_system or None,
                ))
        return rows, stats

    @staticmethod
    def _clause_ref(ob: ExtractedObligation, clause: Clause) -> str:
        """Trust GPT's refinement only when it extends the real clause number (e.g. 4.2 -> 4.2(b))."""
        ref = ob.clause_number or clause.clause_number
        return ref if ref.startswith(clause.clause_number.split("#")[0]) else clause.clause_number

    @staticmethod
    def _verified_citation(ob: ExtractedObligation, clause_text: str) -> tuple[str, bool]:
        """Citation must be verbatim from the clause; otherwise use the best matching mandatory sentence."""
        if ob.citation and loose(ob.citation) and loose(ob.citation) in loose(clause_text):
            return ob.citation, False
        sents = sentences(clause_text)
        pool = [s for s in sents if has_mandatory_language(s)] or sents or [clause_text[:500]]
        req_words = set(loose(ob.requirement).split())
        best = max(pool, key=lambda s: len(req_words & set(loose(s).split())))
        return best, True

    @staticmethod
    def _out(o: ComplianceObligation) -> ObligationOut:
        return ObligationOut(
            id=o.id, clause_ref=o.clause_ref, obligation_text=o.obligation_text, obligation_type=o.obligation_type,
            owner_function=o.owner_function, severity=o.severity, citation=o.citation,
            confidence_score=float(o.confidence_score) if o.confidence_score is not None else None,
            target_system=o.target_system, mapping_status=o.mapping_status or "PENDING", created_at=o.created_at,
        )

    async def _already_extracted(self, doc_code: str, file_hash: str) -> bool:
        last = await self.audit.last_event(doc_code, ["OBLIGATIONS_EXTRACTED"])
        return bool(last and (last.details or {}).get("sha256") == file_hash)

    @staticmethod
    def _ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
