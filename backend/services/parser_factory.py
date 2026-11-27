from __future__ import annotations

from pathlib import PurePosixPath

from services.document_types import DocumentParseError, ParsedDocument
from services.docx_parser import DocxParser
from services.html_parser import HtmlParser
from services.pdf_parser import PdfParser


class ParserFactory:
    """Choose a parser by file extension, falling back to content sniffing."""

    def __init__(self) -> None:
        self._parsers = {"pdf": PdfParser(), "docx": DocxParser(), "html": HtmlParser()}

    @staticmethod
    def sniff(data: bytes) -> str | None:
        """Format from content. Regulator sites often serve HTML viewers or error pages behind '.pdf' links."""
        head = data[:4000]
        if head[:5] == b"%PDF-":
            return "pdf"
        if head[:2] == b"PK" and b"word/" in head:
            return "docx"
        low = head.lower().lstrip()
        if low.startswith((b"<!doctype html", b"<html")) or b"<html" in low[:1000]:
            return "html"
        return None

    @classmethod
    def detect_format(cls, filename: str, data: bytes) -> str:
        found = cls.sniff(data) if data else None
        if found:
            return found
        ext = PurePosixPath(filename or "").suffix.lower()
        if ext == ".pdf":
            return "pdf"
        if ext == ".docx":
            return "docx"
        if ext in {".html", ".htm", ".xhtml"}:
            return "html"
        if ext == ".doc":
            raise DocumentParseError("Legacy .doc is not supported; convert to .docx")
        raise DocumentParseError(f"Unsupported document type: {filename}")

    def parse(self, filename: str, data: bytes) -> ParsedDocument:
        if not data:
            raise DocumentParseError("Document is empty")
        return self._parsers[self.detect_format(filename, data)].parse(data)
