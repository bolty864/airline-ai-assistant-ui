"""Downloads files and pages from regulator websites (DGCA, BCAS, CERT-In, DPDP ...)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from settings import Settings

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,application/xml;q=0.9,*/*;q=0.8",
}


class SourceFetchError(Exception):
    pass


class SourceNotAllowedError(SourceFetchError):
    pass


@dataclass
class FetchedFile:
    data: bytes
    content_type: str | None
    final_url: str


class SourceFetcher:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport  # injectable for tests

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=HEADERS,
            timeout=self.settings.source_timeout_seconds,
            follow_redirects=True,
            verify=self.settings.regulator_tls_verify,
            transport=self.transport,
        )

    def check_allowed(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise SourceNotAllowedError(f"Unsupported URL scheme: {url}")
        allowed = self.settings.allowed_hosts
        host = (parsed.hostname or "").lower()
        if allowed and not any(host == h or host.endswith("." + h) for h in allowed):
            raise SourceNotAllowedError(f"Host not in SOURCE_ALLOWED_HOSTS: {host}")

    async def fetch(self, url: str) -> FetchedFile:
        self.check_allowed(url)
        limit = self.settings.source_max_bytes
        try:
            async with self.client() as client, client.stream("GET", url) as resp:
                resp.raise_for_status()
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > limit:
                        raise SourceFetchError(f"File larger than {limit} bytes: {url}")
                    chunks.append(chunk)
                return FetchedFile(b"".join(chunks), resp.headers.get("content-type"), str(resp.url))
        except httpx.HTTPStatusError as exc:
            raise SourceFetchError(f"Source returned HTTP {exc.response.status_code}: {url}") from exc
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"Source unreachable ({type(exc).__name__}): {url}") from exc

    async def get_text(self, client: httpx.AsyncClient, url: str) -> str:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text
