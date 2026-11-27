"""Regulator crawlers: CERT-In (httpx + BeautifulSoup) and DGCA (Playwright, optional).

Each discovered document goes through the same ingest() as /api/ingest, so change detection,
storage, audit and the Agent 2/3 hand-off are identical.
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from schemas import IngestRequest, IngestResult
from services.source_fetcher import HEADERS, SourceFetcher

log = logging.getLogger(__name__)

IngestFn = Callable[[IngestRequest], Awaitable[IngestResult]]

CERT_IN_BASE = "https://www.cert-in.org.in/"
CERT_IN_LIST = "https://www.cert-in.org.in/s2cMainServlet?pageid=PUBADVLIST"
DGCA_CAR_PAGE = "https://www.dgca.gov.in/digigov-portal/?dynamicPage=civilAviationRequirements/6/0/viewDynamicRulesReq"


def sanitize_doc_code(prefix: str, raw_title: str, url: str) -> str:
    """Stable per URL. The URL hash stops different PDFs that share link text ("View", "Download")
    from overwriting each other as fake DOC_UPDATED events."""
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", raw_title.strip()).strip("_")[:50] or "Document"
    return f"{prefix}_{clean}_{hashlib.sha1(url.encode()).hexdigest()[:8]}"


def _dedupe(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen, out = set(), []
    for title, url in items:
        if url not in seen:
            seen.add(url)
            out.append((title, url))
    return out


async def _ingest_safely(ingest: IngestFn, req: IngestRequest, results: list[dict]) -> None:
    try:
        res = await ingest(req)
        results.append({"doc_code": res.doc_code, "title": req.title, "source_url": req.source_url,
                        "event": res.event})
    except Exception as exc:
        log.warning("Crawl item skipped", extra={"url": req.source_url, "error": str(exc)})
        results.append({"doc_code": req.doc_code, "title": req.title, "source_url": req.source_url,
                        "event": "FAILED", "error": str(exc)[:300]})


async def crawl_cert_in(fetcher: SourceFetcher, ingest: IngestFn, max_items: int = 2,
                        list_url: str = CERT_IN_LIST, base_url: str = CERT_IN_BASE) -> list[dict]:
    results: list[dict] = []
    try:
        async with fetcher.client() as client:
            soup = BeautifulSoup(await fetcher.get_text(client, list_url), "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                href, text = a["href"], a.get_text(strip=True)
                if "PUBVLNOTES" in href or "CIAD-" in text or href.lower().endswith(".pdf"):
                    links.append((text or "CERT_IN_Advisory", urljoin(base_url, href)))

            for title, url in _dedupe(links)[:max_items]:
                pdf_url = url if url.lower().endswith(".pdf") else None
                if pdf_url is None:  # advisory detail page: look for an attached PDF
                    detail = BeautifulSoup(await fetcher.get_text(client, url), "html.parser")
                    tag = detail.find("a", href=re.compile(r"\.pdf$", re.I))
                    pdf_url = urljoin(base_url, tag["href"]) if tag else None
                if not pdf_url:
                    continue
                code = sanitize_doc_code("CERTIN", title, pdf_url)
                await _ingest_safely(ingest, IngestRequest(doc_code=code, filename=f"{code}.pdf", regulator="CERT-IN",
                                                           title=title, source_url=pdf_url), results)
    except Exception as exc:
        log.warning("CERT-In crawl failed", extra={"error": str(exc)})
    return results


async def crawl_dgca(fetcher: SourceFetcher, ingest: IngestFn, max_items: int = 2, page_url: str = DGCA_CAR_PAGE) -> list[dict]:
    """DGCA's portal renders links with JavaScript, so it needs a headless browser.
    Install once:  pip install playwright && playwright install chromium"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("Playwright not installed; DGCA crawl skipped")
        return [{"event": "FAILED", "error": "playwright not installed (pip install playwright && playwright install chromium)"}]

    results: list[dict] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(user_agent=HEADERS["User-Agent"],
                                                    ignore_https_errors=not fetcher.settings.regulator_tls_verify)
                page = await context.new_page()
                await page.goto(page_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)   # dynamic table rows
                links = await page.eval_on_selector_all(
                    "a", "els => els.map(el => ({text: el.innerText.trim(), href: el.href}))")
            finally:
                await browser.close()

        candidates = [(i.get("text") or "DGCA_CAR_Circular", i.get("href", "")) for i in links
                      if ".pdf" in i.get("href", "").lower() or "iframeAttachView" in i.get("href", "")]
        for title, url in _dedupe(candidates)[:max_items]:
            code = sanitize_doc_code("DGCA", title, url)
            await _ingest_safely(ingest, IngestRequest(doc_code=code, filename=f"{code}.pdf", regulator="DGCA",
                                                       title=title, source_url=url), results)
    except Exception as exc:
        log.warning("DGCA crawl failed", extra={"error": str(exc)})
    return results


CRAWLERS = {"CERT-IN": crawl_cert_in, "DGCA": crawl_dgca}
