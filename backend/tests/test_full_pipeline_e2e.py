"""Agent 1 -> Agent 2 -> Agent 3 through the real FastAPI app.

Regulator website: httpx.MockTransport.  Azure Blob: a temp folder.  Azure OpenAI: FakeOpenAI.
Needs Postgres + pgvector:  TEST_DATABASE_URL=postgresql://... pytest -q tests   (wipes that DB)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import psycopg
import pytest

from tests.conftest import FakeOpenAI

BACKEND = Path(__file__).resolve().parents[1]
DOC = "DGCA_CAR_API_Retention"
SOURCE_URL = "https://dgca.test/cars/api-retention.pdf"
PDF = (BACKEND / "sample_data/demo_sources/DGCA_CAR_API_Retention.pdf").read_bytes()


def revised_pdf() -> bytes:
    """A real new version: one more mandatory clause on the last page."""
    import pymupdf

    doc = pymupdf.open(stream=PDF, filetype="pdf")
    doc[-1].insert_text((50, 700), "8.2 Operators shall review API retention settings every 6 months.", fontsize=10)
    return doc.tobytes()

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")


class FakeRegulator:
    """Mutable fake website: tests can change, break or restore what it serves."""

    def __init__(self):
        self.files: dict[str, bytes] = {SOURCE_URL: PDF}
        self.down = False
        self.requests = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        url = str(request.url)
        if self.down:
            return httpx.Response(503, text="maintenance")
        if url.startswith("https://www.cert-in.org.in/s2cMainServlet"):
            return httpx.Response(200, html='<a href="/PDF/CIAD-2026-0042.pdf">CIAD-2026-0042 Advisory</a>'
                                            '<a href="/about">About</a>')
        if url == "https://www.cert-in.org.in/PDF/CIAD-2026-0042.pdf":
            return httpx.Response(200, content=PDF.replace(b"DGCA", b"CERT"),
                                  headers={"content-type": "application/pdf"})
        if url in self.files:
            return httpx.Response(200, content=self.files[url], headers={"content-type": "application/pdf"})
        return httpx.Response(404)


def _reset_db() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        for f in ("001_base_schema.sql", "002_agent3_policy_control_mapping.sql", "003_agent4_gap_assessment.sql", "004_agent5_impact_assessment.sql"):
            conn.execute((BACKEND / "sql" / f).read_text())


def _sql(query: str, *args):
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as conn:
        cur = conn.execute(query, args)
        return cur.fetchall() if cur.description else []


def test_full_pipeline():
    _reset_db()
    asyncio.run(_run())


async def _run():
    import providers
    from agents.pipeline import get_pipeline
    from main import app
    from services.source_fetcher import SourceFetcher
    from settings import get_settings

    fake, site = FakeOpenAI(), FakeRegulator()
    providers.override(llm_client=fake, source_fetcher=SourceFetcher(get_settings(), httpx.MockTransport(site.handler)))
    blob_file = Path(os.environ["LOCAL_STORAGE_ROOT"]) / f"{DOC}.pdf"
    pipeline = get_pipeline()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=60) as c:
        assert (await c.post("/api/mapping/ingest")).status_code == 200

        # ---- Agent 1 NEW_DOC -> Agent 2 -> Agent 3 (wait=true runs the chain inline)
        body = {"doc_code": DOC, "filename": f"{DOC}.pdf", "regulator": "dgca",
                "title": "CAR Section 3 Series M Part IV - API", "source_url": SOURCE_URL, "wait": True}
        r = await c.post("/api/ingest", json=body)
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["event"] == "NEW_DOC" and res["version_tag"] == "v1.0" and blob_file.read_bytes() == PDF
        assert res["extraction"]["status"] == "COMPLETED" and res["extraction"]["obligations_extracted"] == 7
        assert res["extraction"]["mapping_queued"] is True
        impact = {o["clause"]: o for o in (await c.get(f"/api/mapping/impact/{DOC}")).json()}
        assert "CTRL-001" in {x["code"] for x in impact["4.2"]["controls"]}

        # ---- Agent 4 ran after mapping: CTRL-001 keeps records 3 years, the regulation wants 5
        await pipeline.drain()
        gaps = {g["clause_ref"]: g for g in (await c.get(f"/api/gaps/{res['document_id']}")).json()["assessments"]}
        assert gaps and all(g["risk_rating"] in {"CRITICAL", "HIGH", "MEDIUM", "LOW"} for g in gaps.values())

        # ---- unchanged at source: no new LLM calls
        calls = len(fake.calls)
        res = (await c.post("/api/ingest", json=body)).json()
        assert res["event"] == "DOC_UNCHANGED" and res["extraction"]["status"] == "SKIPPED_UNCHANGED"
        assert len(fake.calls) == calls

        # ---- healthy scan
        scan = (await c.post("/api/watchdog/scan")).json()
        assert scan == {**scan, "scanned": 1, "healthy": 1, "healed": 0}

        # ---- demo: delete the blob -> watchdog restores it and re-runs Agents 2+3
        r = await c.post("/api/demo/simulate-delete", json={"doc_code": DOC})
        assert r.json()["existed"] is True and not blob_file.exists()
        scan = (await c.post("/api/watchdog/scan")).json()
        assert scan["healed"] == 1 and scan["actions"][0]["reason"] == "File missing from repository"
        assert blob_file.read_bytes() == PDF
        await pipeline.drain()
        assert len(fake.calls) > calls  # forced re-extraction after heal (SELF_HEAL_FORCE_REEXTRACT)
        assert all(s == "MAPPED" or s == "NEEDS_REVIEW"
                   for (s,) in _sql("SELECT mapping_status FROM compliance_obligations"))

        # ---- tampered file (checksum mismatch) is healed too
        blob_file.write_bytes(b"%PDF-1.4 tampered")
        scan = (await c.post("/api/watchdog/scan")).json()
        assert scan["healed"] == 1 and scan["actions"][0]["reason"] == "Checksum mismatch"
        assert blob_file.read_bytes() == PDF
        await pipeline.drain()

        # ---- regulator publishes a new version -> DOC_UPDATED, version bump, re-extraction
        site.files[SOURCE_URL] = revised_pdf()
        res = (await c.post("/api/ingest", json=body)).json()
        assert res["event"] == "DOC_UPDATED" and res["version_tag"] == "v1.1"
        assert res["extraction"]["reprocessed"] is True and res["extraction"]["obligations_extracted"] == 8
        PDF_NOW = site.files[SOURCE_URL]

        # ---- source down while the blob is missing -> HEAL_FAILED, MISSING, retried only after back-off
        site.down = True
        blob_file.unlink()
        scan = (await c.post("/api/watchdog/scan")).json()
        assert scan["failed"] == 1 and "503" in scan["actions"][0]["error"]
        docs = (await c.get("/api/documents")).json()
        assert docs["documents"][0]["status"] == "MISSING" and docs["documents"][0]["obligation_count"] == 8
        assert (await c.post(f"/api/obligations/extract/{res['document_id']}")).status_code == 409
        assert (await c.post("/api/watchdog/scan")).json()["scanned"] == 0   # back-off respected
        site.down = False
        _sql("UPDATE regulatory_documents SET last_verified_at = NOW() - INTERVAL '1 hour'")  # pretend time passed
        scan = (await c.post("/api/watchdog/scan")).json()
        assert scan["healed"] == 1 and blob_file.read_bytes() == PDF_NOW
        await pipeline.drain()

        # ---- CERT-In crawler -> ingest -> background pipeline
        r = await c.post("/api/crawl/trigger", json={"regulators": ["CERT-IN", "DPDP"], "max_items": 2})
        crawl = r.json()
        assert crawl["total_processed"] == 1 and crawl["not_supported"] == ["DPDP"]
        assert crawl["ingested_documents"]["CERT-IN"][0]["doc_code"].startswith("CERTIN_CIAD_2026_0042_Advisory_")
        await pipeline.drain()

        # ---- read APIs
        docs = (await c.get("/api/documents", params={"regulator": "CERT-IN"})).json()
        assert docs["total"] == 1 and docs["documents"][0]["obligation_count"] == 7
        obs = (await c.get(f"/api/documents/{DOC}/obligations")).json()
        assert obs["obligations_count"] == 8
        health = (await c.get("/api/health")).json()
        assert health["database_connected"] and health["blob_storage_connected"] and health["storage_mode"] == "local"
        logs = (await c.get("/api/audit-logs", params={"doc_code": DOC, "limit": 200})).json()["logs"]
        events = {l["event_type"] for l in logs}
        assert {"NEW_DOC", "DOC_UNCHANGED", "MISSING_DETECTED", "SELF_HEALED", "DOC_UPDATED", "HEAL_FAILED",
                "OBLIGATIONS_EXTRACTED", "OBLIGATIONS_REPROCESSED", "OBLIGATIONS_MAPPED"} <= events

        # ---- error mapping
        assert (await c.post("/api/demo/simulate-delete", json={"doc_code": "NOPE"})).status_code == 404
        bad = {**body, "doc_code": "BROKEN", "source_url": "https://dgca.test/missing.pdf"}
        assert (await c.post("/api/ingest", json=bad)).json()["error"] == "source_unreachable"
        assert (await c.post("/api/ingest", json={**body, "source_url": "file:///etc/passwd"})).status_code == 400

    providers.reset()
