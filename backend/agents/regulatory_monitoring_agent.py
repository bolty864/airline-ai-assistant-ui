"""Agent 1: Regulatory Monitoring Agent.

* ingest():  download from the regulator, detect NEW / UPDATED / UNCHANGED by sha256, store in Blob,
             register in regulatory_documents.
* scan():    self-healing watchdog. Detects missing or tampered files, re-downloads them from the
             source, restores the blob and hands the document to Agents 2+3 again.

It no longer extracts obligations itself; that is Agent 2's job (see agents/pipeline.py).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from pathlib import PurePosixPath

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from models import RegulatoryDocument
from repositories import AuditRepository, DocumentRepository
from schemas import HealAction, IngestRequest, IngestResult, ScanResult
from services.blob_storage import BlobStorageService
from services.parser_factory import ParserFactory
from services.source_fetcher import SourceFetcher
from services.text_utils import sha256_bytes
from settings import Settings

log = logging.getLogger(__name__)

_EXT = {"pdf": ".pdf", "docx": ".docx", "html": ".html"}
_scan_lock = asyncio.Lock()   # one scan at a time (background watchdog + manual /api/watchdog/scan)

OnDocumentChanged = Callable[[int, bool, str], None]   # (document_id, force, reason)


class DocumentNotRegisteredError(Exception):
    pass


def bump_version(tag: str | None) -> str:
    m = re.fullmatch(r"v?(\d+)\.(\d+)", (tag or "").strip())
    return f"v{m.group(1)}.{int(m.group(2)) + 1}" if m else "v1.1"


class RegulatoryMonitoringAgent:
    def __init__(
        self,
        session: AsyncSession,
        documents: DocumentRepository,
        audit: AuditRepository,
        blob: BlobStorageService,
        fetcher: SourceFetcher,
        parsers: ParserFactory,
        settings: Settings,
    ):
        self.session = session
        self.documents = documents
        self.audit = audit
        self.blob = blob
        self.fetcher = fetcher
        self.parsers = parsers
        self.settings = settings

    # ------------------------------------------------------------------ ingestion & change detection

    async def ingest(self, req: IngestRequest) -> IngestResult:
        fetched = await self.fetcher.fetch(req.source_url)
        data = fetched.data
        fmt = self.parsers.detect_format(req.filename, data)        # by content first: catches HTML error pages
        filename = self._filename(req.filename, fmt)
        sha = sha256_bytes(data)
        details: dict = {"filename": filename, "hash": sha[:12], "format": fmt, "bytes": len(data)}
        requested_ext = PurePosixPath(req.filename).suffix.lower()
        if requested_ext and requested_ext not in {_EXT[fmt], ".htm"}:
            details["warning"] = f"Expected {requested_ext}, source returned {fmt}"

        doc = await self.documents.get_by_doc_code(req.doc_code)
        if doc is None:
            await self.blob.upload(filename, data, sha, fetched.content_type)
            doc = await self.documents.create(
                doc_code=req.doc_code, filename=filename, regulator=req.regulator.upper(), title=req.title,
                source_url=req.source_url, blob_path=filename, sha256_hash=sha, status="ACTIVE",
            )
            event = "NEW_DOC"
        elif doc.sha256_hash != sha:
            await self.blob.upload(doc.blob_path, data, sha, fetched.content_type)
            details.update(old_hash=doc.sha256_hash[:12], new_hash=sha[:12], old_version=doc.version_tag)
            doc.sha256_hash = sha
            doc.version_tag = bump_version(doc.version_tag)
            doc.title, doc.source_url, doc.status = req.title, req.source_url, "ACTIVE"
            doc.updated_at = doc.last_verified_at = func.now()
            event = "DOC_UPDATED"
        else:
            state = await self.blob.state(doc.blob_path, sha)
            if not state.matches(sha):          # registry is fine but the blob is not: repair it now
                await self.blob.upload(doc.blob_path, data, sha, fetched.content_type)
                details["blob_restored"] = True
            doc.status = "ACTIVE"
            doc.last_verified_at = func.now()
            event = "DOC_UNCHANGED"

        result = IngestResult(
            document_id=doc.id, doc_code=doc.doc_code, event=event, changed=event != "DOC_UNCHANGED",
            sha256_hash=sha, version_tag=doc.version_tag, blob_path=doc.blob_path, format=fmt,
        )
        details["version"] = result.version_tag
        await self.audit.log(event, req.doc_code, details)
        await self.session.commit()
        log.info("Document ingested", extra={"doc_code": req.doc_code, "event": event})
        return result

    @staticmethod
    def _filename(requested: str, fmt: str) -> str:
        stem = re.sub(r"[^A-Za-z0-9_\-.]+", "_", PurePosixPath(requested).stem).strip("_") or "document"
        return stem + _EXT[fmt]

    # ------------------------------------------------------------------ self-healing watchdog

    async def scan(self, on_document_changed: OnDocumentChanged | None = None) -> ScanResult:
        if _scan_lock.locked():
            return ScanResult(scanned=0, healthy=0, healed=0, failed=0, skipped=True)
        async with _scan_lock:
            started = time.perf_counter()
            docs = await self.documents.list_for_watchdog(
                self.settings.heal_retry_seconds, self.settings.stale_healing_seconds)
            healthy_ids: list[int] = []
            actions: list[HealAction] = []

            for doc in docs:
                try:
                    state = await self.blob.state(doc.blob_path, doc.sha256_hash)
                except Exception:
                    # Storage itself is unreachable: never mark everything missing because of an outage
                    log.exception("Blob check failed", extra={"doc_code": doc.doc_code})
                    continue
                if doc.status == "ACTIVE" and state.matches(doc.sha256_hash):
                    healthy_ids.append(doc.id)
                    continue
                if doc.status != "ACTIVE":
                    reason = f"Retrying heal (status {doc.status})"
                elif not state.exists:
                    reason = "File missing from repository"
                else:
                    reason = "Checksum mismatch"
                actions.append(await self._heal(doc, reason, on_document_changed))

            await self.documents.touch_verified(healthy_ids)
            await self.session.commit()
            healed = sum(a.outcome == "SELF_HEALED" for a in actions)
            return ScanResult(
                scanned=len(docs), healthy=len(healthy_ids), healed=healed, failed=len(actions) - healed,
                actions=actions, scan_duration_ms=int((time.perf_counter() - started) * 1000),
            )

    async def _heal(self, doc: RegulatoryDocument, reason: str, on_changed: OnDocumentChanged | None) -> HealAction:
        doc_id, doc_code, old_sha = doc.id, doc.doc_code, doc.sha256_hash
        blob_path, source_url = doc.blob_path, doc.source_url

        # 1. detect + mark HEALING (Agent 2 refuses HEALING docs, so nothing reads a half-restored file)
        await self.audit.log("MISSING_DETECTED", doc_code, {"filename": doc.filename, "reason": reason})
        doc.status = "HEALING"
        doc.last_verified_at = func.now()
        await self.session.commit()
        log.warning("Self-healing started", extra={"doc_code": doc_code, "reason": reason})

        try:
            # 2-3. verify source + re-download + restore
            fetched = await self.fetcher.fetch(source_url)
            sha = sha256_bytes(fetched.data)
            await self.blob.upload(blob_path, fetched.data, sha, fetched.content_type)
            source_changed = sha != old_sha

            doc.status = "ACTIVE"
            doc.sha256_hash = sha
            doc.last_verified_at = func.now()
            if source_changed:   # regulator published a new version while our copy was gone
                doc.version_tag = bump_version(doc.version_tag)
                doc.updated_at = func.now()
            await self.audit.log("SELF_HEALED", doc_code, {
                "restored_from": source_url, "verified_hash": sha[:12], "source_changed": source_changed})
            if source_changed:
                await self.audit.log("DOC_UPDATED", doc_code, {
                    "old_hash": old_sha[:12], "new_hash": sha[:12], "detected_by": "self_heal"})
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            fresh = await self.documents.get_by_id(doc_id)
            if fresh is not None:
                fresh.status = "MISSING"
                fresh.last_verified_at = func.now()    # back-off clock for the next retry
            await self.audit.log("HEAL_FAILED", doc_code, {
                "error": str(exc)[:500], "next_retry_in_seconds": self.settings.heal_retry_seconds})
            await self.session.commit()
            log.error("Self-healing failed", extra={"doc_code": doc_code, "error": str(exc)})
            return HealAction(doc_code=doc_code, reason=reason, outcome="HEAL_FAILED", error=str(exc)[:500])

        # 4-5. re-index and re-run obligations (Agents 2 + 3), refreshes compliance status
        if on_changed:
            on_changed(doc_id, self.settings.self_heal_force_reextract, "self_heal")
        return HealAction(doc_code=doc_code, reason=reason, outcome="SELF_HEALED", source_changed=source_changed)

    # ------------------------------------------------------------------ demo

    async def simulate_delete(self, doc_code: str) -> dict:
        doc = await self.documents.get_by_doc_code(doc_code)
        if doc is None:
            raise DocumentNotRegisteredError(f"Document '{doc_code}' not registered")
        deleted = await self.blob.delete(doc.blob_path)
        await self.audit.log("DEMO_BLOB_DELETED", doc_code, {"blob_path": doc.blob_path, "existed": deleted})
        await self.session.commit()
        return {
            "message": "Simulated deletion complete. File removed from storage.",
            "doc_code": doc_code,
            "deleted_blob": doc.filename,
            "existed": deleted,
            "note": f"Self-healing watchdog will detect and restore it within "
                    f"{self.settings.watchdog_interval_seconds} seconds.",
        }
