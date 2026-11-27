"""HTML text extraction with BeautifulSoup (regulator web pages, notifications)."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString

from services.document_types import DocumentParseError, ParsedDocument

_NOISE_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe", "svg", "button"]
_BLOCK_TAGS = ["p", "div", "section", "article", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "pre",
               "blockquote", "dd", "dt", "table", "ul", "ol"]


class HtmlParser:
    def parse(self, data: bytes) -> ParsedDocument:
        try:
            soup = BeautifulSoup(data, "lxml")
        except Exception:
            soup = BeautifulSoup(data, "html.parser")

        for tag in soup(_NOISE_TAGS):
            tag.decompose()
        root = soup.find("main") or soup.find("article") or soup.body or soup

        # Ordered lists: restore "(a)" style markers so sub-clauses survive
        for ol in root.find_all("ol"):
            for i, li in enumerate(ol.find_all("li", recursive=False)):
                li.insert(0, NavigableString(f"({chr(97 + i % 26)}) "))
        for cell in root.find_all(["td", "th"]):
            cell.append(NavigableString(" | "))
        for tag in root.find_all(_BLOCK_TAGS):
            tag.insert_before(NavigableString("\n"))
            tag.insert_after(NavigableString("\n"))

        raw = root.get_text()
        lines = [re.sub(r"[ \t ]+", " ", ln).strip().rstrip("|").strip() for ln in raw.splitlines()]
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
        if not text:
            raise DocumentParseError("HTML contains no readable text")
        return ParsedDocument(text=text, format="html")
