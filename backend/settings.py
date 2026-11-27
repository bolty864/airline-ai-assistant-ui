"""Application settings, loaded from environment variables or a .env file."""
from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "AeroComply AI"
    environment: str = "dev"
    log_level: str = "INFO"
    log_json: bool = True

    # Database (plain postgresql:// URL; the SQLAlchemy driver is added automatically)
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/aerocomply",
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_DSN"),
    )
    db_pool_size: int = 10
    db_max_overflow: int = 10

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_key: str = Field(default="", validation_alias=AliasChoices("AZURE_OPENAI_KEY", "AZURE_OPENAI_API_KEY"))
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_embedding_deployment: str = Field(
        default="text-embedding-3-small",
        validation_alias=AliasChoices("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "EMBEDDING_MODEL"),
    )
    openai_timeout_seconds: int = 90
    openai_max_retries: int = 5

    # Storage for regulatory documents (Agent 1 writes, Agent 2 reads)
    azure_storage_connection_string: str | None = None
    regulatory_blob_container: str = "regulatory-docs"
    local_storage_root: str | None = None  # dev: use a local folder instead of Azure Blob

    # Agent 1: monitoring, ingestion, self-healing
    watchdog_enabled: bool = True
    watchdog_interval_seconds: int = 5        # demo value; 60+ is plenty in production
    heal_retry_seconds: int = 300             # back-off before retrying a failed heal
    stale_healing_seconds: int = 600          # HEALING longer than this (crash mid-heal) is retried
    self_heal_force_reextract: bool = True    # re-run Agents 2/3 even when the restored file is identical
    regulator_tls_verify: bool = True         # some regulator sites have broken TLS chains; set false only if needed
    source_timeout_seconds: int = 30
    source_max_bytes: int = 50 * 1024 * 1024
    source_allowed_hosts: str = ""            # comma separated allow-list for /api/ingest; empty = any host
    demo_endpoints_enabled: bool = True       # /api/demo/* (simulate delete, offline demo sources)
    cors_origins: str = "*"

    # Agent 2 tuning
    extraction_concurrency: int = 5
    extraction_min_confidence: float = 0.50
    max_clause_chars: int = 6000
    max_completion_tokens: int = 2000

    # Agent 1 -> Agent 2 -> Agent 3 hand-off
    pipeline_concurrency: int = 2             # documents processed in parallel by Agents 2+3
    auto_map_after_extraction: bool = True
    auto_assess_after_mapping: bool = True    # Agent 3 -> Agent 4
    auto_impact_after_assessment: bool = True # Agent 4 -> Agent 5

    # Agent 4: compliance gap assessment
    gap_concurrency: int = 5
    gap_max_completion_tokens: int = 1800
    gap_review_confidence: float = 0.70       # findings below this are flagged needs_review
    gap_param_mismatch_cap: float = 60.0      # coverage ceiling when a required number/period/deadline is not met
    gap_failed_test_cap: float = 49.0         # coverage ceiling when the control failed its last test
    gap_escalate_high_severity: bool = True   # MEDIUM -> HIGH for shall/must obligations (see README, risk rules)
    gap_require_evidence: bool = True         # controls without an evidence source get an Evidence Missing gap

    # Agent 5: regulatory change impact & remediation
    impact_concurrency: int = 4
    impact_max_completion_tokens: int = 1800
    impact_match_threshold: float = 0.55      # similarity needed to treat an old and a new clause as the same obligation
    impact_review_confidence: float = 0.70    # impacts below this are flagged needs_review
    impact_first_version_as_new: bool = True  # no previous version: every obligation counts as NEW_OBLIGATION
    impact_max_tasks_per_impact: int = 5
    obligation_versions_keep: int = 5         # previous versions kept per document
    agent3_worker_enabled: bool = True
    agent3_poll_seconds: int = 20

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        for prefix in ("postgresql+psycopg://", "postgresql+asyncpg://", "postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def allowed_hosts(self) -> set[str]:
        return {h.strip().lower() for h in self.source_allowed_hosts.split(",") if h.strip()}

    @property
    def psycopg_url(self) -> str:
        return self.sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
