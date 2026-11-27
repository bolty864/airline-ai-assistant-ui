from __future__ import annotations

from functools import lru_cache

from openai import AsyncAzureOpenAI

from settings import get_settings


class OpenAIConfigError(RuntimeError):
    pass


@lru_cache
def get_openai_client() -> AsyncAzureOpenAI:
    s = get_settings()
    if not (s.azure_openai_endpoint and s.azure_openai_key):
        raise OpenAIConfigError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY must be set")
    return AsyncAzureOpenAI(
        azure_endpoint=s.azure_openai_endpoint,
        api_key=s.azure_openai_key,
        api_version=s.azure_openai_api_version,
        timeout=s.openai_timeout_seconds,
        max_retries=s.openai_max_retries,  # SDK retries 429/5xx with exponential backoff
    )
