"""Agent 3: Policy & Control Mapping Agent.

Pipeline per obligation
  1. embed obligation (cached; reuses Agent 2's embedding if present)
  2. retrieve candidates with SQL only (hybrid search + control/system graph expansion)
  3. skip LLM if nothing is even remotely similar -> UNMAPPED (Gap Agent treats as Non-Compliant)
  4. gpt-4o-mini selects + justifies mappings (strict JSON schema, short candidate ids)
  5. escalate to gpt-4o only for CRITICAL / low-confidence / empty results
  6. validate (no invented ids, verbatim provision check) and persist + audit
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field

from . import db
from .config import Settings
from .llm import Embedder
from .retriever import Candidate, Retriever

log = logging.getLogger("agent3.mapper")

SYSTEM_PROMPT = """You are the Policy & Control Mapping Agent of an airline regulatory compliance platform \
(regulators: DGCA, BCAS, ICAO, IATA, CERT-In, DPDP).

Given ONE regulatory obligation and candidate internal assets (policy sections [P], controls [C], systems [S]), \
select every asset a compliance officer must review, update or use as evidence to implement this obligation.

Rules
- Use only candidate_id values from the list. Never invent assets.
- link_type:
  DIRECT     = the asset itself states a rule on the same requirement (same data / activity / parameter), \
even if its current value differs from the regulation.
  SUPPORTING = the asset implements, enforces, stores or processes what the obligation is about \
(e.g. the system holding the data, the control enforcing the retention).
  CONTEXTUAL = related; unlikely to need change.
- relevance: 0.0 to 1.0, your confidence that the asset is impacted.
- current_provision: copy VERBATIM the sentence from the candidate text that currently addresses the requirement \
(e.g. the existing retention period). Empty string if the candidate has no such sentence. Never paraphrase.
- Do NOT judge compliance or severity. Gap analysis is done by another agent.
- Prefer precision. Leave out candidates that are only topically similar.
- If nothing is impacted return an empty mappings list and explain why in unmapped_reason.
- rationale: one short sentence."""

MAPPING_SCHEMA = {
    "name": "obligation_mapping",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["mappings", "unmapped_reason"],
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["candidate_id", "link_type", "relevance", "current_provision", "rationale"],
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "link_type": {"type": "string", "enum": ["DIRECT", "SUPPORTING", "CONTEXTUAL"]},
                        "relevance": {"type": "number"},
                        "current_provision": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                },
            },
            "unmapped_reason": {"type": "string"},
        },
    },
}


@dataclass
class MappingResult:
    obligation_id: int
    doc_code: str
    status: str
    model: str | None
    mappings: list[dict] = field(default_factory=list)
    note: str = ""
    escalated: bool = False


class PolicyControlMappingAgent:
    def __init__(self, settings: Settings, client, embedder: Embedder):
        self.s = settings
        self.client = client
        self.embedder = embedder
        self.retriever = Retriever(settings)
        self.usage: dict[str, dict[str, int]] = {}

    # ------------------------------------------------------------------ public API

    async def map_pending(self, conn, limit: int | None = None) -> dict:
        ids = await self._claim(conn, "mapping_status = 'PENDING'", (), limit or self.s.batch_size)
        return await self._run(conn, ids)

    async def map_document(self, conn, doc_code: str) -> dict:
        ids = await self._claim(
            conn,
            "document_id = (SELECT id FROM regulatory_documents WHERE doc_code = %s) AND mapping_status <> 'MAPPING'",
            (doc_code,), None,
        )
        return await self._run(conn, ids)

    async def map_obligations(self, conn, obligation_ids: list[int]) -> dict:
        ids = await self._claim(conn, "id = ANY(%s) AND mapping_status <> 'MAPPING'", (obligation_ids,), None)
        return await self._run(conn, ids)

    # ------------------------------------------------------------------ pipeline

    async def _claim(self, conn, where: str, params: tuple, limit: int | None) -> list[int]:
        """Atomically mark obligations as MAPPING so parallel workers never double-process."""
        lim = f"LIMIT {int(limit)}" if limit else ""
        cur = await conn.execute(
            f"""
            UPDATE compliance_obligations SET mapping_status = 'MAPPING'
            WHERE id IN (SELECT id FROM compliance_obligations WHERE {where}
                         ORDER BY id {lim} FOR UPDATE SKIP LOCKED)
            RETURNING id
            """,
            params,
        )
        return [r["id"] for r in await cur.fetchall()]

    async def _run(self, conn, ids: list[int]) -> dict:
        if not ids:
            return {"processed": 0}
        self.usage = {}
        tokens_before = self.embedder.tokens_used
        try:
            obligations = await self._load(conn, ids)
            await self._ensure_embeddings(conn, obligations)

            # Retrieval is cheap SQL; run sequentially on the single connection
            prepared = [(ob, await self.retriever.candidates(conn, ob, ob["embedding"])) for ob in obligations]

            sem = asyncio.Semaphore(self.s.max_concurrency)

            async def guarded(ob, cands):
                async with sem:
                    try:
                        return await self._map_one(ob, cands)
                    except Exception as exc:
                        log.exception("Mapping failed for obligation %s", ob["id"])
                        return MappingResult(ob["id"], ob["doc_code"], "ERROR", None, note=str(exc)[:500])

            results = await asyncio.gather(*(guarded(ob, c) for ob, c in prepared))
            cands_by_ob = {ob["id"]: {c.key: c for c in cands} for ob, cands in prepared}
            for res in results:
                await self._persist(conn, res, cands_by_ob[res.obligation_id])
        except Exception:
            await conn.execute(
                "UPDATE compliance_obligations SET mapping_status = 'PENDING' WHERE id = ANY(%s) AND mapping_status = 'MAPPING'",
                (ids,),
            )
            raise

        summary = self._summarise(results, cands_by_ob, self.embedder.tokens_used - tokens_before)
        for doc_code, details in summary["by_document"].items():
            await db.audit(conn, "OBLIGATIONS_MAPPED", doc_code, {**details, "llm_usage": summary["llm_usage"]})
        return summary

    async def _load(self, conn, ids: list[int]) -> list[dict]:
        cur = await conn.execute(
            """
            SELECT o.id, o.clause_ref, o.obligation_text, o.obligation_type, o.target_system, o.severity,
                   o.owner_function, o.citation, o.embedding, d.doc_code, d.regulator, d.title AS regulation_title
            FROM compliance_obligations o JOIN regulatory_documents d ON d.id = o.document_id
            WHERE o.id = ANY(%s) ORDER BY o.id
            """,
            (ids,),
        )
        return list(await cur.fetchall())

    async def _ensure_embeddings(self, conn, obligations: list[dict]) -> None:
        missing = [ob for ob in obligations if ob["embedding"] is None]
        if not missing:
            return
        vecs = await self.embedder.embed_many(conn, [ob["obligation_text"] for ob in missing])
        for ob, vec in zip(missing, vecs):
            ob["embedding"] = vec
            await conn.execute("UPDATE compliance_obligations SET embedding = %s WHERE id = %s", (vec, ob["id"]))

    async def _map_one(self, ob: dict, cands: list[Candidate]) -> MappingResult:
        best_sim = max((c.similarity for c in cands), default=0.0)
        if not cands or best_sim < self.s.similarity_floor:
            return MappingResult(ob["id"], ob["doc_code"], "UNMAPPED", None,
                                 note=f"No internal asset above similarity floor (best={best_sim:.2f})")

        by_key = {c.key: c for c in cands}
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": self._render(ob, cands)}]

        model = self.s.mapping_model
        raw = await self._call(model, messages)
        mappings = self._validate(raw, by_key)
        escalated = False

        top = max((m["relevance"] for m in mappings), default=0.0)
        severity = (ob.get("severity") or "").upper()
        if self.s.escalation_model and self.s.escalation_model != model and (
            severity in self.s.escalate_severities or top < self.s.escalation_threshold
        ):
            model = self.s.escalation_model
            raw = await self._call(model, messages)
            mappings = self._validate(raw, by_key)
            top = max((m["relevance"] for m in mappings), default=0.0)
            escalated = True

        if not mappings:
            status = "UNMAPPED"
        elif top < self.s.review_threshold:
            status = "NEEDS_REVIEW"
        else:
            status = "MAPPED"
        return MappingResult(ob["id"], ob["doc_code"], status, model, mappings,
                             note=raw.get("unmapped_reason", "") if not mappings else "", escalated=escalated)

    def _render(self, ob: dict, cands: list[Candidate]) -> str:
        lines = [
            "OBLIGATION",
            f"Regulator: {ob.get('regulator')} | Document: {ob.get('regulation_title')} | Clause: {ob.get('clause_ref') or 'n/a'}",
            f"Type: {ob.get('obligation_type') or 'n/a'} | Owner: {ob.get('owner_function') or 'n/a'} | "
            f"Target system (from extraction): {ob.get('target_system') or 'n/a'}",
            f"Text: {ob['obligation_text']}",
        ]
        if ob.get("citation"):
            lines.append(f"Source citation: {ob['citation'][:600]}")
        lines.append("\nCANDIDATES")
        for c in cands:
            snippet = re.sub(r"\s+", " ", c.content)[: self.s.snippet_chars]
            lines.append(f"[{c.key}] {c.label}\n{snippet}")
        return "\n".join(lines)

    async def _call(self, model: str, messages: list[dict]) -> dict:
        resp = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=1500,
            response_format={"type": "json_schema", "json_schema": MAPPING_SCHEMA},
        )
        if resp.usage:
            u = self.usage.setdefault(model, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})
            u["calls"] += 1
            u["prompt_tokens"] += resp.usage.prompt_tokens
            u["completion_tokens"] += resp.usage.completion_tokens
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)

    def _validate(self, raw: dict, by_key: dict[str, Candidate]) -> list[dict]:
        out, seen = [], set()
        for m in raw.get("mappings", []):
            key = str(m.get("candidate_id", "")).strip().strip("[]").upper()
            cand = by_key.get(key)
            if cand is None or key in seen:
                continue  # hallucinated or duplicate id
            rel = min(max(float(m.get("relevance", 0)), 0.0), 1.0)
            if rel < self.s.min_relevance:
                continue
            seen.add(key)
            provision = (m.get("current_provision") or "").strip()
            if provision and _norm(provision) not in _norm(cand.content):
                provision = ""  # not verbatim, so it can't be trusted as evidence
            out.append({
                "key": key,
                "link_type": m.get("link_type", "CONTEXTUAL"),
                "relevance": rel,
                "current_provision": provision,
                "rationale": (m.get("rationale") or "")[:1000],
            })
        return out

    async def _persist(self, conn, res: MappingResult, by_key: dict[str, Candidate]) -> None:
        async with conn.transaction():
            await conn.execute("DELETE FROM obligation_mappings WHERE obligation_id = %s", (res.obligation_id,))
            for m in res.mappings:
                c = by_key[m["key"]]
                await conn.execute(
                    """
                    INSERT INTO obligation_mappings (obligation_id, target_type, target_id, target_code, target_doc_code,
                        link_type, relevance_score, vector_similarity, current_provision, rationale, model_used)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (res.obligation_id, c.target_type, c.target_id, c.target_code, c.target_doc_code,
                     m["link_type"], round(m["relevance"] * 100, 2), round(c.similarity, 4),
                     m["current_provision"] or None, m["rationale"], res.model),
                )
            await conn.execute(
                "UPDATE compliance_obligations SET mapping_status = %s, mapped_at = NOW(), mapping_model = %s WHERE id = %s",
                (res.status, res.model, res.obligation_id),
            )
        if res.status in {"NEEDS_REVIEW", "UNMAPPED", "ERROR"}:
            await db.audit(conn, f"MAPPING_{res.status}", res.doc_code,
                           {"obligation_id": res.obligation_id, "note": res.note, "model": res.model})

    def _summarise(self, results: list[MappingResult], cands_by_ob: dict, embed_tokens: int) -> dict:
        def view(r: MappingResult, m: dict) -> dict:
            c = cands_by_ob[r.obligation_id][m["key"]]
            return {"target_type": c.target_type, "target_code": c.target_code, "target_name": c.label,
                    "link_type": m["link_type"], "relevance": round(m["relevance"] * 100, 2),
                    "current_provision": m["current_provision"], "rationale": m["rationale"]}

        by_doc: dict[str, dict] = {}
        for r in results:
            d = by_doc.setdefault(r.doc_code, {"obligations": 0, "mappings": 0, "escalated": 0, "status": {}})
            d["obligations"] += 1
            d["mappings"] += len(r.mappings)
            d["escalated"] += int(r.escalated)
            d["status"][r.status] = d["status"].get(r.status, 0) + 1
        return {
            "processed": len(results),
            "by_document": by_doc,
            "llm_usage": self.usage,
            "embedding_tokens": embed_tokens,
            "results": [
                {"obligation_id": r.obligation_id, "status": r.status, "model": r.model, "escalated": r.escalated,
                 "mappings": [view(r, m) for m in r.mappings],
                 "note": r.note}
                for r in results
            ],
        }


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
