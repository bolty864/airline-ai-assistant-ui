"""Shared runtime used by the API, CLI and background worker."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from . import db
from .config import Settings, load_settings
from .ingest import ingest_enterprise
from .llm import Embedder, make_client
from .mapper import PolicyControlMappingAgent
from .sources import make_source

log = logging.getLogger("agent3")


class Agent3Service:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self._client = None
        # Set by the app: called with the doc_codes the background worker just mapped
        self.on_documents_mapped: Callable[[list[str]], Awaitable[None]] | None = None

    @property
    def client(self):
        if self._client is None:
            if not self.settings.api_key:
                raise RuntimeError("Set AZURE_OPENAI_API_KEY (or OPENAI_API_KEY) for Agent 3")
            self._client = make_client(self.settings)
        return self._client

    def _agent(self) -> PolicyControlMappingAgent:
        return PolicyControlMappingAgent(self.settings, self.client, Embedder(self.client, self.settings.embedding_model))

    async def ingest(self) -> dict:
        async with db.connect(self.settings.database_url) as conn:
            return await ingest_enterprise(conn, Embedder(self.client, self.settings.embedding_model),
                                           make_source(self.settings))

    async def map_pending(self, limit: int | None = None) -> dict:
        async with db.connect(self.settings.database_url) as conn:
            return await self._agent().map_pending(conn, limit)

    async def map_document(self, doc_code: str) -> dict:
        async with db.connect(self.settings.database_url) as conn:
            return await self._agent().map_document(conn, doc_code)

    async def map_obligations(self, ids: list[int]) -> dict:
        async with db.connect(self.settings.database_url) as conn:
            return await self._agent().map_obligations(conn, ids)

    async def impact(self, doc_code: str) -> list[dict]:
        """Grouped view: one entry per obligation with its policies, controls and systems."""
        async with db.connect(self.settings.database_url) as conn:
            cur = await conn.execute(
                """
                SELECT o.id AS obligation_id, o.clause_ref, o.obligation_text, o.severity, o.mapping_status,
                       v.target_type, v.target_code, v.target_name, v.section_ref, v.section_heading, v.link_type,
                       v.relevance_score, v.current_provision, v.rationale, v.review_status
                FROM compliance_obligations o
                JOIN regulatory_documents rd ON rd.id = o.document_id
                LEFT JOIN v_obligation_impact v ON v.obligation_id = o.id
                WHERE rd.doc_code = %s
                ORDER BY o.id, v.relevance_score DESC NULLS LAST
                """,
                (doc_code,),
            )
            rows = await cur.fetchall()
        grouped: dict[int, dict] = {}
        bucket = {"POLICY_SECTION": "policies", "CONTROL": "controls", "SYSTEM": "systems"}
        for r in rows:
            g = grouped.setdefault(r["obligation_id"], {
                "obligation_id": r["obligation_id"], "clause": r["clause_ref"], "obligation": r["obligation_text"],
                "severity": r["severity"], "mapping_status": r["mapping_status"],
                "policies": [], "controls": [], "systems": [],
            })
            if r["target_type"]:
                g[bucket[r["target_type"]]].append({
                    "code": r["target_code"], "name": r["target_name"], "section": r["section_ref"],
                    "heading": r["section_heading"], "link_type": r["link_type"],
                    "relevance": float(r["relevance_score"]), "current_provision": r["current_provision"],
                    "rationale": r["rationale"], "review_status": r["review_status"],
                })
        return list(grouped.values())

    async def set_review(self, mapping_id: int, status: str) -> bool:
        async with db.connect(self.settings.database_url) as conn:
            cur = await conn.execute(
                "UPDATE obligation_mappings SET review_status = %s WHERE id = %s RETURNING id", (status, mapping_id)
            )
            return (await cur.fetchone()) is not None

    async def worker(self, interval_s: int = 20) -> None:
        """Polls the queue. Agent 2 inserts obligations as PENDING; self-heal re-inserts them as PENDING too."""
        if not self.settings.api_key:
            log.warning("Agent 3 worker not started: AZURE_OPENAI_KEY is not set")
            return
        log.info("Agent 3 worker started (every %ss)", interval_s)
        while True:
            try:
                res = await self.map_pending()
                if res.get("processed"):
                    log.info("Mapped %s obligations: %s", res["processed"], res["by_document"])
                    if self.on_documents_mapped:
                        await self.on_documents_mapped(list(res["by_document"]))
                    continue  # drain the queue before sleeping
            except Exception:
                log.exception("Worker iteration failed")
            await asyncio.sleep(interval_s)
