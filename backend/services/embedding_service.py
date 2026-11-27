"""Azure OpenAI text-embedding-3-small, batched, with a shared Postgres cache."""
from __future__ import annotations

import logging

from repositories.embedding_cache_repository import EmbeddingCacheRepository
from services.text_utils import normalize, sha256_text

log = logging.getLogger(__name__)

BATCH_SIZE = 96


class EmbeddingService:
    def __init__(self, client, deployment: str, cache: EmbeddingCacheRepository):
        self.client = client
        self.deployment = deployment
        self.cache = cache
        self.tokens_used = 0
        self.cache_hits = 0

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        norm = [normalize(t) for t in texts]
        hashes = [sha256_text(t) for t in norm]
        unique = dict(zip(hashes, norm))

        found = await self.cache.get_many(self.deployment, list(unique))
        self.cache_hits += len(found)
        todo = [h for h in unique if h not in found]

        for i in range(0, len(todo), BATCH_SIZE):
            batch = todo[i:i + BATCH_SIZE]
            resp = await self.client.embeddings.create(model=self.deployment, input=[unique[h] or " " for h in batch])
            if resp.usage:
                self.tokens_used += resp.usage.total_tokens
            new = [(h, item.embedding) for h, item in zip(batch, sorted(resp.data, key=lambda d: d.index))]
            found.update(new)
            await self.cache.put_many(self.deployment, new)

        return [found[h] for h in hashes]
