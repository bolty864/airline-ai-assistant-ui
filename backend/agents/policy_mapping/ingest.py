"""Index the internal enterprise repository: policies/SOPs (chunked) + control & system registers."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from pathlib import PurePosixPath

from . import db
from .documents import chunk_document, embedding_text, extract_lines, select_publishable
from .llm import Embedder, sha256_text

log = logging.getLogger("agent3.ingest")
REGISTER_FOLDER = "control_registers"


async def ingest_enterprise(conn, embedder: Embedder, source, archive_missing: bool = True) -> dict:
    paths = await source.list()
    doc_files = [p for p in paths if not p.startswith(REGISTER_FOLDER + "/")]
    register_files = [p for p in paths if p.startswith(REGISTER_FOLDER + "/")]

    summary = {"indexed": [], "unchanged": [], "archived": [], "failed": [], "chunks": 0,
               "systems": 0, "controls": 0, "obligations_requeued": 0}

    publishable = select_publishable(doc_files)
    for info in publishable:
        try:
            await _ingest_document(conn, embedder, source, info, summary)
        except Exception as exc:  # keep going, one bad file must not block the repo
            log.exception("Failed to index %s", info.path)
            summary["failed"].append({"path": info.path, "error": str(exc)})

    if archive_missing:
        seen = [i.doc_code for i in publishable]
        cur = await conn.execute(
            "UPDATE enterprise_documents SET status = 'ARCHIVED', updated_at = NOW() "
            "WHERE status = 'ACTIVE' AND NOT (doc_code = ANY(%s)) RETURNING id, doc_code",
            (seen,),
        )
        archived = await cur.fetchall()
        for row in archived:
            summary["obligations_requeued"] += await _requeue_for_document(conn, row["id"])
            summary["archived"].append(row["doc_code"])

    systems, controls = await _load_registers(source, register_files)
    summary["systems"] = await _upsert_systems(conn, embedder, systems)
    summary["controls"] = await _upsert_controls(conn, embedder, controls)

    summary["embedding_tokens"] = embedder.tokens_used
    await db.audit(conn, "ENTERPRISE_REINDEXED", "ENTERPRISE_REPOSITORY", summary)
    return summary


async def _ingest_document(conn, embedder, source, info, summary) -> None:
    data = await source.read(info.path)
    file_hash = hashlib.sha256(data).hexdigest()
    cur = await conn.execute(
        "SELECT id, sha256_hash, status FROM enterprise_documents WHERE doc_code = %s", (info.doc_code,)
    )
    existing = await cur.fetchone()
    if existing and existing["sha256_hash"] == file_hash and existing["status"] == "ACTIVE":
        summary["unchanged"].append(info.doc_code)
        return

    title, chunks = chunk_document(extract_lines(info.path, data))
    title = title or info.doc_code.replace("_", " ").title()
    if not chunks:
        raise ValueError("No text extracted")

    vectors = await embedder.embed_many(conn, [embedding_text(title, c) for c in chunks])
    filename = PurePosixPath(info.path).name

    async with conn.transaction():
        if existing:
            summary["obligations_requeued"] += await _requeue_for_document(conn, existing["id"])
            await conn.execute("DELETE FROM enterprise_chunks WHERE document_id = %s", (existing["id"],))
            await conn.execute(
                "UPDATE enterprise_documents SET doc_type=%s, title=%s, filename=%s, blob_path=%s, version_tag=%s, "
                "sha256_hash=%s, status='ACTIVE', indexed_at=NOW(), updated_at=NOW() WHERE id=%s",
                (info.doc_type, title, filename, source.blob_path(info.path), info.version_tag, file_hash, existing["id"]),
            )
            doc_id = existing["id"]
        else:
            cur = await conn.execute(
                "INSERT INTO enterprise_documents (doc_code, doc_type, title, filename, blob_path, version_tag, sha256_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (info.doc_code, info.doc_type, title, filename, source.blob_path(info.path), info.version_tag, file_hash),
            )
            doc_id = (await cur.fetchone())["id"]

        async with conn.cursor() as c:
            await c.executemany(
                "INSERT INTO enterprise_chunks (document_id, chunk_index, section_ref, heading, content, content_hash, embedding) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                [
                    (doc_id, ch.index, ch.section_ref, ch.heading, ch.content, sha256_text(ch.content), vec)
                    for ch, vec in zip(chunks, vectors)
                ],
            )
        await db.audit(conn, "ENTERPRISE_DOC_INDEXED", info.doc_code,
                       {"version": info.version_tag, "chunks": len(chunks), "path": info.path})

    summary["indexed"].append(info.doc_code)
    summary["chunks"] += len(chunks)


async def _requeue_for_document(conn, document_id: int) -> int:
    """A policy changed: its old mappings are stale, so send affected obligations back to the queue."""
    cur = await conn.execute(
        """
        WITH stale AS (
            DELETE FROM obligation_mappings m
            USING enterprise_chunks c
            WHERE m.target_type = 'POLICY_SECTION' AND m.target_id = c.id AND c.document_id = %s
            RETURNING m.obligation_id
        )
        UPDATE compliance_obligations SET mapping_status = 'PENDING'
        WHERE id IN (SELECT obligation_id FROM stale)
        RETURNING id
        """,
        (document_id,),
    )
    return len(await cur.fetchall())


# ---------------------------- registers ----------------------------

async def _load_registers(source, paths: list[str]) -> tuple[list[dict], list[dict]]:
    systems, controls = [], []
    for path in paths:
        name = PurePosixPath(path).name.lower()
        raw = await source.read(path)
        if name.endswith(".json"):
            rows = json.loads(raw.decode("utf-8"))
        elif name.endswith(".csv"):
            rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
            for r in rows:  # CSV lists are ';' separated
                for key in ("aliases", "data_categories", "systems"):
                    if isinstance(r.get(key), str):
                        r[key] = [x.strip() for x in r[key].split(";") if x.strip()]
        else:
            continue
        if "system" in name:
            systems.extend(rows)
        elif "control" in name:
            controls.extend(rows)
    return systems, controls


def _system_text(s: dict) -> str:
    aliases = ", ".join(s.get("aliases") or [])
    data = ", ".join(s.get("data_categories") or [])
    return (f"System: {s['name']}" + (f" (also known as {aliases})" if aliases else "")
            + f"\nOwner: {s.get('owner_function') or 'n/a'}\nData handled: {data or 'n/a'}\n{s.get('description') or ''}")


def _control_text(c: dict) -> str:
    return (f"Control {c['control_code']}: {c['name']}\nType: {c.get('control_type') or 'n/a'}; "
            f"Owner: {c.get('owner_function') or 'n/a'}; Frequency: {c.get('frequency') or 'n/a'}\n"
            f"{c.get('description') or ''}")


async def _upsert_systems(conn, embedder, systems: list[dict]) -> int:
    if not systems:
        return 0
    vectors = await embedder.embed_many(conn, [_system_text(s) for s in systems])
    async with conn.transaction():
        for s, vec in zip(systems, vectors):
            await conn.execute(
                """
                INSERT INTO systems (system_code, name, description, aliases, data_categories, owner_function, embedding,
                                     criticality)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (system_code) DO UPDATE SET name=EXCLUDED.name, description=EXCLUDED.description,
                    aliases=EXCLUDED.aliases, data_categories=EXCLUDED.data_categories,
                    owner_function=EXCLUDED.owner_function, embedding=EXCLUDED.embedding,
                    criticality=EXCLUDED.criticality, status='ACTIVE', updated_at=NOW()
                """,
                (s["system_code"], s["name"], s.get("description"), s.get("aliases") or [],
                 s.get("data_categories") or [], s.get("owner_function"), vec,
                 (s.get("criticality") or "").upper() or None),
            )
    return len(systems)


async def _upsert_controls(conn, embedder, controls: list[dict]) -> int:
    if not controls:
        return 0
    vectors = await embedder.embed_many(conn, [_control_text(c) for c in controls])
    async with conn.transaction():
        for c, vec in zip(controls, vectors):
            cur = await conn.execute(
                """
                INSERT INTO controls (control_code, name, description, control_type, owner_function, frequency,
                                      policy_doc_code, embedding, automation_level, evidence_source,
                                      last_evidence_at, test_result)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (control_code) DO UPDATE SET name=EXCLUDED.name, description=EXCLUDED.description,
                    control_type=EXCLUDED.control_type, owner_function=EXCLUDED.owner_function,
                    frequency=EXCLUDED.frequency, policy_doc_code=EXCLUDED.policy_doc_code,
                    embedding=EXCLUDED.embedding, automation_level=EXCLUDED.automation_level,
                    evidence_source=EXCLUDED.evidence_source, last_evidence_at=EXCLUDED.last_evidence_at,
                    test_result=EXCLUDED.test_result, status='ACTIVE', updated_at=NOW()
                RETURNING id
                """,
                (c["control_code"], c["name"], c.get("description"), c.get("control_type"), c.get("owner_function"),
                 c.get("frequency"), (c.get("policy_doc_code") or "").upper() or None, vec,
                 (c.get("automation_level") or "").upper() or None, c.get("evidence_source") or None,
                 c.get("last_evidence_at") or None, (c.get("test_result") or "").upper() or None),
            )
            control_id = (await cur.fetchone())["id"]
            await conn.execute("DELETE FROM control_system_links WHERE control_id = %s", (control_id,))
            if c.get("systems"):
                await conn.execute(
                    "INSERT INTO control_system_links (control_id, system_id) "
                    "SELECT %s, id FROM systems WHERE system_code = ANY(%s) ON CONFLICT DO NOTHING",
                    (control_id, [x.upper() for x in c["systems"]]),
                )
    return len(controls)
