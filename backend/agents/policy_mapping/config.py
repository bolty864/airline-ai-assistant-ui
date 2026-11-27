"""Runtime settings, all overridable through environment variables (.env supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # optional
    pass


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _i(name: str, default: int) -> int:
    return int(os.getenv(name, default))


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_key: str
    azure_endpoint: str | None
    azure_api_version: str
    openai_base_url: str | None

    # Models (for Azure these are DEPLOYMENT names)
    embedding_model: str
    mapping_model: str          # cheap + accurate reranker / mapper
    escalation_model: str       # used only for hard / critical cases

    # Retrieval
    top_k_policy: int
    top_k_controls: int
    top_k_systems: int
    retrieval_pool: int         # candidates per retriever before fusion
    similarity_floor: float     # below this, skip the LLM entirely (nothing relevant)
    snippet_chars: int

    # Decision thresholds (0-1)
    min_relevance: float        # drop LLM mappings below this
    escalation_threshold: float # best mapping below this -> second opinion with escalation model
    review_threshold: float     # best mapping below this -> NEEDS_REVIEW
    escalate_severities: tuple[str, ...]

    max_concurrency: int
    batch_size: int

    # Enterprise repository source
    enterprise_source: str      # 'local' or 'blob'
    enterprise_local_path: str
    blob_connection_string: str | None
    blob_container: str
    blob_prefix: str


def _psycopg_url(url: str) -> str:
    for prefix in ("postgresql+psycopg://", "postgresql+asyncpg://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def load_settings() -> Settings:
    # Same env vars as Agent 2 (AZURE_OPENAI_KEY / AZURE_OPENAI_DEPLOYMENT / AZURE_OPENAI_EMBEDDING_DEPLOYMENT)
    api_key = (os.getenv("AZURE_OPENAI_KEY") or os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "")
    return Settings(
        database_url=_psycopg_url(os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN") or "postgresql://postgres:postgres@localhost:5432/aerocomply"),
        api_key=api_key,
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT") or None,
        azure_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
        embedding_model=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT") or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        mapping_model=os.getenv("MAPPING_MODEL", "gpt-4o-mini"),
        escalation_model=os.getenv("ESCALATION_MODEL") or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        top_k_policy=_i("TOP_K_POLICY", 6),
        top_k_controls=_i("TOP_K_CONTROLS", 5),
        top_k_systems=_i("TOP_K_SYSTEMS", 4),
        retrieval_pool=_i("RETRIEVAL_POOL", 20),
        similarity_floor=_f("SIMILARITY_FLOOR", 0.20),
        snippet_chars=_i("SNIPPET_CHARS", 900),
        min_relevance=_f("MIN_RELEVANCE", 0.50),
        escalation_threshold=_f("ESCALATION_THRESHOLD", 0.65),
        review_threshold=_f("REVIEW_THRESHOLD", 0.75),
        escalate_severities=tuple(
            s.strip().upper() for s in os.getenv("ESCALATE_SEVERITIES", "CRITICAL").split(",") if s.strip()
        ),
        max_concurrency=_i("MAX_CONCURRENCY", 8),
        batch_size=_i("MAPPING_BATCH_SIZE", 50),
        enterprise_source=os.getenv("ENTERPRISE_SOURCE", "local"),
        enterprise_local_path=os.getenv("ENTERPRISE_LOCAL_PATH", "./sample_data/enterprise"),
        blob_connection_string=os.getenv("AZURE_STORAGE_CONNECTION_STRING") or None,
        blob_container=os.getenv("ENTERPRISE_BLOB_CONTAINER", "enterprise"),
        blob_prefix=os.getenv("ENTERPRISE_BLOB_PREFIX", ""),
    )
