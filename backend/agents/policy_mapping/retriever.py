"""Candidate retrieval: hybrid (vector + full-text) for policy sections, vector + graph expansion
for controls and systems. Everything here is pure SQL, so it costs no LLM tokens."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

STOPWORDS = {
    "the", "and", "for", "shall", "must", "with", "from", "that", "this", "are", "all", "any", "not", "such",
    "within", "under", "per", "each", "into", "been", "have", "has", "will", "may", "should", "their", "its",
    "which", "who", "where", "when", "than", "other", "also", "including", "required", "requirement",
}
RRF_K = 60


@dataclass
class Candidate:
    key: str                  # short id shown to the LLM: P1, C2, S3
    target_type: str          # POLICY_SECTION, CONTROL, SYSTEM
    target_id: int
    target_code: str
    target_doc_code: str | None
    label: str
    content: str
    similarity: float
    signals: list[str] = field(default_factory=list)   # why it was retrieved (vector, keyword, linked, hint)


def build_tsquery(text: str, limit: int = 24) -> str | None:
    words, seen = [], set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]{1,}", text.lower()):
        if (len(w) < 3 and not w.isupper()) or w in STOPWORDS or w in seen:
            continue
        seen.add(w)
        words.append(w)
    return " | ".join(words[:limit]) if words else None


def rrf_fuse(*ranked_lists: list[int]) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked):
            scores[item] = scores.get(item, 0.0) + 1.0 / (RRF_K + rank + 1)
    return scores


class Retriever:
    def __init__(self, settings):
        self.s = settings
        self._systems_cache: list[dict] | None = None

    async def candidates(self, conn, obligation: dict, qvec) -> list[Candidate]:
        query_text = " ".join(filter(None, [obligation.get("obligation_text"), obligation.get("obligation_type"),
                                            obligation.get("target_system")]))
        policies = await self._policy_sections(conn, qvec, query_text)
        doc_codes = sorted({p.target_doc_code for p in policies if p.target_doc_code})
        controls = await self._controls(conn, qvec, doc_codes)
        systems = await self._systems(conn, qvec, [c.target_id for c in controls], obligation.get("target_system"))

        out: list[Candidate] = []
        for prefix, items in (("P", policies), ("C", controls), ("S", systems)):
            for i, c in enumerate(items, 1):
                c.key = f"{prefix}{i}"
                out.append(c)
        return out

    async def _policy_sections(self, conn, qvec, query_text: str) -> list[Candidate]:
        pool = self.s.retrieval_pool
        base = """
            SELECT c.id, c.section_ref, c.heading, c.content, d.doc_code, d.title, d.version_tag,
                   1 - (c.embedding <=> %(q)s::vector) AS sim
            FROM enterprise_chunks c JOIN enterprise_documents d ON d.id = c.document_id
            WHERE d.status = 'ACTIVE' AND c.embedding IS NOT NULL
        """
        cur = await conn.execute(base + " ORDER BY c.embedding <=> %(q)s::vector LIMIT %(n)s", {"q": qvec, "n": pool})
        vec_rows = await cur.fetchall()

        kw_rows = []
        tsq = build_tsquery(query_text)
        if tsq:
            cur = await conn.execute(
                base + " AND c.content_tsv @@ to_tsquery('english', %(t)s) "
                       "ORDER BY ts_rank_cd(c.content_tsv, to_tsquery('english', %(t)s)) DESC LIMIT %(n)s",
                {"q": qvec, "t": tsq, "n": pool},
            )
            kw_rows = await cur.fetchall()

        rows = {r["id"]: r for r in vec_rows + kw_rows}
        vec_ids = [r["id"] for r in vec_rows]
        kw_ids = [r["id"] for r in kw_rows]
        fused = rrf_fuse(vec_ids, kw_ids)
        top = sorted(fused, key=fused.get, reverse=True)[: self.s.top_k_policy]

        out = []
        for cid in top:
            r = rows[cid]
            signals = (["vector"] if cid in vec_ids else []) + (["keyword"] if cid in kw_ids else [])
            ref = r["section_ref"] or f"chunk{cid}"
            section = f" § {r['heading']}" if r["heading"] else ""
            out.append(Candidate("", "POLICY_SECTION", cid, f"{r['doc_code']}#{ref}", r["doc_code"],
                                 f"{r['title']} ({r['version_tag']}){section}", r["content"], float(r["sim"]), signals))
        return out

    async def _controls(self, conn, qvec, doc_codes: list[str]) -> list[Candidate]:
        cur = await conn.execute(
            """
            SELECT id, control_code, name, description, owner_function, policy_doc_code,
                   1 - (embedding <=> %(q)s::vector) AS sim, 'vector' AS via
            FROM controls WHERE status = 'ACTIVE' AND embedding IS NOT NULL
            ORDER BY embedding <=> %(q)s::vector LIMIT %(k)s
            """,
            {"q": qvec, "k": self.s.top_k_controls},
        )
        rows = await cur.fetchall()
        if doc_codes:  # graph expansion: controls that implement the retrieved policies
            cur = await conn.execute(
                """
                SELECT id, control_code, name, description, owner_function, policy_doc_code,
                       1 - (embedding <=> %(q)s::vector) AS sim, 'linked_policy' AS via
                FROM controls WHERE status = 'ACTIVE' AND policy_doc_code = ANY(%(d)s)
                ORDER BY embedding <=> %(q)s::vector LIMIT 3
                """,
                {"q": qvec, "d": doc_codes},
            )
            rows += await cur.fetchall()
        return self._dedupe(rows, lambda r: Candidate(
            "", "CONTROL", r["id"], r["control_code"], r["policy_doc_code"],
            f"{r['control_code']} {r['name']} (owner: {r['owner_function'] or 'n/a'})",
            r["description"] or r["name"], float(r["sim"]), [r["via"]]))

    async def _systems(self, conn, qvec, control_ids: list[int], target_system: str | None) -> list[Candidate]:
        cols = "s.id, s.system_code, s.name, s.description, s.data_categories, 1 - (s.embedding <=> %(q)s::vector) AS sim"
        cur = await conn.execute(
            f"SELECT {cols}, 'vector' AS via FROM systems s WHERE s.status='ACTIVE' AND s.embedding IS NOT NULL "
            "ORDER BY s.embedding <=> %(q)s::vector LIMIT %(k)s",
            {"q": qvec, "k": self.s.top_k_systems},
        )
        rows = await cur.fetchall()
        if control_ids:  # systems where the candidate controls operate
            cur = await conn.execute(
                f"SELECT DISTINCT {cols}, 'linked_control' AS via FROM systems s "
                "JOIN control_system_links l ON l.system_id = s.id "
                "WHERE s.status='ACTIVE' AND l.control_id = ANY(%(c)s) LIMIT 4",
                {"q": qvec, "c": control_ids},
            )
            rows += await cur.fetchall()
        hint_ids = await self._hinted_system_ids(conn, target_system)
        if hint_ids:  # Agent 2 already named the target system
            cur = await conn.execute(f"SELECT {cols}, 'agent2_hint' AS via FROM systems s WHERE s.id = ANY(%(i)s)",
                                     {"q": qvec, "i": hint_ids})
            rows += await cur.fetchall()
        return self._dedupe(rows, lambda r: Candidate(
            "", "SYSTEM", r["id"], r["system_code"], None, r["name"],
            f"{r['description'] or ''} Data: {', '.join(r['data_categories'] or []) or 'n/a'}",
            float(r["sim"]), [r["via"]]))

    async def _hinted_system_ids(self, conn, target_system: str | None) -> list[int]:
        if not target_system:
            return []
        if self._systems_cache is None:
            cur = await conn.execute("SELECT id, name, system_code, aliases FROM systems WHERE status='ACTIVE'")
            self._systems_cache = await cur.fetchall()
        hint_tokens = _tokens(target_system)
        ids = []
        for s in self._systems_cache:
            names = [s["name"], s["system_code"].replace("_", " "), *(s["aliases"] or [])]
            if any(_tokens(n) and (_tokens(n) <= hint_tokens or hint_tokens <= _tokens(n)) for n in names) \
                    or any(n.lower() in target_system.lower() for n in names if len(n) >= 3):
                ids.append(s["id"])
        return ids

    @staticmethod
    def _dedupe(rows, make) -> list[Candidate]:
        merged: dict[int, Candidate] = {}
        for r in rows:
            c = make(r)
            if c.target_id in merged:
                for sig in c.signals:
                    if sig not in merged[c.target_id].signals:
                        merged[c.target_id].signals.append(sig)
            else:
                merged[c.target_id] = c
        return sorted(merged.values(), key=lambda c: c.similarity, reverse=True)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3 and t != "system"}
