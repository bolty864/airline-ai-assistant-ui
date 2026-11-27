"""PDF text extraction with PyMuPDF, with repeating header/footer removal and de-hyphenation."""
from __future__ import annotations

import logging
import re
from collections import Counter

try:
    import pymupdf
except ImportError:  # older PyMuPDF releases
    import fitz as pymupdf  # type: ignore[no-redef]

from services.document_types import DocumentParseError, ParsedDocument

log = logging.getLogger(__name__)

_EDGE_LINES = 3                     # lines at top/bottom of a page checked for headers/footers
_PAGE_NO = re.compile(r"^(page\s*)?\d+(\s*(of|/)\s*\d+)?$", re.I)


class PdfParser:
    def parse(self, data: bytes) -> ParsedDocument:
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise DocumentParseError(f"Invalid PDF: {exc}") from exc

        with doc:
            if doc.needs_pass:
                raise DocumentParseError("PDF is password protected")
            pages = [self._page_lines(page) for page in doc]

        if not any(pages):
            raise DocumentParseError("PDF has no text layer (scanned document); OCR is required")

        warnings: list[str] = []
        empty = sum(1 for p in pages if not p)
        if empty:
            warnings.append(f"{empty} page(s) without extractable text")

        noise = self._repeating_edges(pages)
        cleaned: list[str] = []
        for lines in pages:
            for i, line in enumerate(lines):
                at_edge = i < _EDGE_LINES or i >= len(lines) - _EDGE_LINES
                if at_edge and (_PAGE_NO.match(line) or self._key(line) in noise):
                    continue
                cleaned.append(line)
            cleaned.append("")  # page break acts as paragraph break

        text = self._dehyphenate("\n".join(cleaned))
        return ParsedDocument(text=text, format="pdf", page_count=len(pages), warnings=warnings)

    @staticmethod
    def _page_lines(page) -> list[str]:
        text = page.get_text("text", sort=True)
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    @staticmethod
    def _key(line: str) -> str:
        return re.sub(r"\d+", "#", line.lower())

    def _repeating_edges(self, pages: list[list[str]]) -> set[str]:
        if len(pages) < 3:
            return set()
        counts: Counter[str] = Counter()
        for lines in pages:
            edges = {self._key(l) for l in lines[:_EDGE_LINES] + lines[-_EDGE_LINES:]}
            counts.update(edges)
        threshold = max(2, int(len(pages) * 0.5))
        return {k for k, n in counts.items() if n >= threshold}

    @staticmethod
    def _dehyphenate(text: str) -> str:
        # "reten-\ntion" -> "retention" (only when the next line starts lowercase)
        return re.sub(r"(\w)-\n(?=[a-z])", r"\1", text)
