"""DOCX text extraction with python-docx (paragraphs and tables in document order).

Word auto-numbering is not part of paragraph text, so clause numbers like "4.2" would be lost.
We rebuild decimal numbering from the list levels (numPr/ilvl) as a best effort.
"""
from __future__ import annotations

import io
import logging

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from services.document_types import DocumentParseError, ParsedDocument

log = logging.getLogger(__name__)


class DocxParser:
    def parse(self, data: bytes) -> ParsedDocument:
        try:
            doc = Document(io.BytesIO(data))
        except Exception as exc:
            raise DocumentParseError(f"Invalid DOCX: {exc}") from exc

        lines: list[str] = []
        counters: dict[str, list[int]] = {}
        for child in doc.element.body.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                para = Paragraph(child, doc)
                text = para.text.strip()
                if not text:
                    lines.append("")
                    continue
                number = self._list_number(para, counters)
                lines.append(f"{number} {text}" if number and not text[:1].isdigit() else text)
            elif tag == "tbl":
                lines.extend(self._table_lines(Table(child, doc)))
                lines.append("")

        text = "\n".join(lines).strip()
        if not text:
            raise DocumentParseError("DOCX contains no text")
        return ParsedDocument(text=text, format="docx")

    @staticmethod
    def _num_pr(element):
        ppr = element.find(qn("w:pPr")) if element is not None else None
        return ppr.find(qn("w:numPr")) if ppr is not None else None

    @classmethod
    def _list_number(cls, para: Paragraph, counters: dict[str, list[int]]) -> str | None:
        num_pr = cls._num_pr(para._p)
        if num_pr is None and para.style is not None:  # numbering inherited from the style ("List Number")
            num_pr = cls._num_pr(para.style.element)
        if num_pr is None:
            return None
        num_id_el, ilvl_el = num_pr.find(qn("w:numId")), num_pr.find(qn("w:ilvl"))
        if num_id_el is None:
            return None
        num_id = num_id_el.get(qn("w:val"))
        level = int(ilvl_el.get(qn("w:val"))) if ilvl_el is not None else 0
        if num_id == "0":
            return None
        stack = counters.setdefault(num_id, [])
        while len(stack) <= level:
            stack.append(0)
        del stack[level + 1:]
        stack[level] += 1
        nums = [n if n else 1 for n in stack]
        return ".".join(str(n) for n in nums) + ("." if level == 0 else "")

    @staticmethod
    def _table_lines(table: Table) -> list[str]:
        out = []
        for row in table.rows:
            cells: list[str] = []
            for cell in row.cells:
                t = cell.text.strip()
                if t and (not cells or cells[-1] != t):  # merged cells repeat their text
                    cells.append(t)
            if cells:
                out.append(" | ".join(cells))
        return out
