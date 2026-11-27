"""OpenAI / Azure OpenAI client and a cached, batched embedder."""
from __future__ import annotations

import numpy as np
from openai import AsyncAzureOpenAI, AsyncOpenAI

from services.text_utils import normalize, sha256_text  # shared with Agent 2 => shared embedding cache

from .config import Settings

EMBED_BATCH = 96


def make_client(s: Settings):
    if s.azure_endpoint:
        return AsyncAzureOpenAI(
            api_key=s.api_key,
            azure_endpoint=s.azure_endpoint,
            api_version=s.azure_api_version,
            max_retries=5,
            timeout=60,
        )
    return AsyncOpenAI(api_key=s.api_key, base_url=s.openai_base_url, max_retries=5, timeout=60)


class Embedder:
    """text-embedding-3-small with a Postgres-backed cache.

    Identical text is never embedded twice, so self-heal re-runs and
    re-ingests of unchanged policies cost zero embedding tokens.
    """

    def __init__(self, client, model: str):
        self.client = client
        self.model = model
        self.tokens_used = 0

    async def embed_many(self, conn, texts: list[str]) -> list[np.ndarray]:
        norm = [normalize(t) for t in texts]
        hashes = [sha256_text(t) for t in norm]
        unique = dict(zip(hashes, norm))

        found: dict[str, np.ndarray] = {}
        if unique:
            cur = await conn.execute(
                "SELECT content_hash, embedding FROM embedding_cache WHERE model = %s AND content_hash = ANY(%s)",
                (self.model, list(unique)),
            )
            found = {r["content_hash"]: r["embedding"] for r in await cur.fetchall()}

        todo = [h for h in unique if h not in found]
        for i in range(0, len(todo), EMBED_BATCH):
            batch = todo[i : i + EMBED_BATCH]
            resp = await self.client.embeddings.create(model=self.model, input=[unique[h] or " " for h in batch])
            if resp.usage:
                self.tokens_used += resp.usage.total_tokens
            rows = []
            for h, item in zip(batch, sorted(resp.data, key=lambda d: d.index)):
                vec = np.asarray(item.embedding, dtype=np.float32)
                found[h] = vec
                rows.append((h, self.model, vec))
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO embedding_cache (content_hash, model, embedding) VALUES (%s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    rows,
                )
        return [found[h] for h in hashes]

    async def embed_one(self, conn, text: str) -> np.ndarray:
        return (await self.embed_many(conn, [text]))[0]
