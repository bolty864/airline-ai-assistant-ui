"""Composition root: shared singletons for the API, background jobs and the watchdog.

Tests (or a demo without Azure) can swap implementations with providers.override(...),
which also reaches background tasks, unlike FastAPI's dependency_overrides.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from services.blob_storage import BlobStorageService
from services.parser_factory import ParserFactory
from services.source_fetcher import SourceFetcher
from settings import get_settings

_overrides: dict[str, Any] = {}


def override(**items: Any) -> None:
    _overrides.update(items)


def reset() -> None:
    _overrides.clear()


def llm_client():
    if "llm_client" in _overrides:
        return _overrides["llm_client"]
    from services.openai_client import get_openai_client

    return get_openai_client()


def source_fetcher() -> SourceFetcher:
    return _overrides.get("source_fetcher") or _default_fetcher()


def agent3_service():
    from agents.policy_mapping.api import get_service

    svc = get_service()
    if "llm_client" in _overrides:
        svc._client = _overrides["llm_client"]
    return svc


@lru_cache
def blob_service() -> BlobStorageService:
    return BlobStorageService(get_settings())


@lru_cache
def parser_factory() -> ParserFactory:
    return ParserFactory()


@lru_cache
def _default_fetcher() -> SourceFetcher:
    return SourceFetcher(get_settings())
