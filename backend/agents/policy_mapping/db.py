"""Async Postgres + pgvector helpers."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import psycopg
from pgvector.psycopg import register_vector_async
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


@asynccontextmanager
async def connect(dsn: str):
    conn = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row, autocommit=True)
    try:
        await register_vector_async(conn)
        yield conn
    finally:
        await conn.close()


async def audit(conn, event_type: str, doc_code: str, details: dict[str, Any]) -> None:
    await conn.execute(
        "INSERT INTO agent_audit_logs (event_type, doc_code, details) VALUES (%s, %s, %s)",
        (event_type, doc_code, Jsonb(details)),
    )
