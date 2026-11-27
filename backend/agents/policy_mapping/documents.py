"""Parse policy files (md/txt/docx/pdf) into section-aware chunks."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
NUM_HEADING = re.compile(r"^(\d+(?:\.\d+){0,3})[.)]?\s+(.{2,120})$")
REF_PREFIX = re.compile(r"^(?:section\s+|clause\s+)?(\d+(?:\.\d+){0,3})[.)]?\s+", re.I)
NAME_RE = re.compile(
    r"^(?P<code>.+?)(?:[_-]v(?P<ver>\d+(?:\.\d+)?))?(?:[_-](?P<status>DRAFT|APPROVED|ACTIVE|ARCHIVED|FINAL))?$",
    re.I,
)

SUPPORTED_EXT = {".md", ".txt", ".docx", ".pdf"}
DOC_TYPE_BY_FOLDER = {
    "policies": "POLICY",
    "sops": "SOP",
    "audit_procedures": "AUDIT_PROCEDURE",
    "security_standards": "SECURITY_STANDARD",
}


@dataclass
class Chunk:
    index: int
    section_ref: str | None
    heading: str
    content: str


@dataclass
class FileInfo:
    path: str
    doc_code: str
    version: tuple[int, ...]
    version_tag: str
    status: str
    doc_type: str


def parse_filename(path: str) -> FileInfo | None:
    p = PurePosixPath(path.replace("\\", "/"))
    if p.suffix.lower() not in SUPPORTED_EXT:
        return None
    m = NAME_RE.match(p.stem)
    if not m:
        return None
    ver = m.group("ver") or "1.0"
    folder = p.parent.name.lower() if p.parent.name else ""
    if folder not in DOC_TYPE_BY_FOLDER:  # only the known repository folders are indexed
        return None
    return FileInfo(
        path=str(p),
        doc_code=m.group("code").upper().replace("-", "_").replace(" ", "_"),
        version=tuple(int(x) for x in ver.split(".")),
        version_tag=f"v{ver}" if "." in ver else f"v{ver}.0",
        status=(m.group("status") or "APPROVED").upper(),
        doc_type=DOC_TYPE_BY_FOLDER[folder],
    )


def select_publishable(paths: list[str]) -> list[FileInfo]:
    """Keep only the highest non-draft version per doc_code.

    Drafts belong to the review workflow (Agents 5-7) and must never be
    treated as the airline's current position.
    """
    best: dict[str, FileInfo] = {}
    for path in paths:
        info = parse_filename(path)
        if not info or info.status in {"DRAFT", "ARCHIVED"}:
            continue
        cur = best.get(info.doc_code)
        if cur is None or info.version > cur.version:
            best[info.doc_code] = info
    return list(best.values())


def extract_lines(filename: str, data: bytes) -> list[str]:
    ext = PurePosixPath(filename).suffix.lower()
    if ext in {".md", ".txt"}:
        return data.decode("utf-8", errors="ignore").splitlines()
    if ext == ".docx":
        return _docx_lines(data)
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        lines: list[str] = []
        for page in reader.pages:
            lines.extend((page.extract_text() or "").splitlines())
            lines.append("")
        return lines
    raise ValueError(f"Unsupported file type: {filename}")


def _docx_lines(data: bytes) -> list[str]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(io.BytesIO(data))
    lines: list[str] = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            text = p.text.strip()
            style = (p.style.name if p.style is not None else "") or ""
            if text and (style.startswith("Heading") or style == "Title"):
                digits = "".join(ch for ch in style if ch.isdigit())
                level = int(digits) if digits else 1
                lines.append("#" * min(level, 6) + " " + text)
            else:
                lines.append(text)
        elif tag == "tbl":
            for row in Table(child, doc).rows:
                cells = []
                for c in row.cells:
                    t = c.text.strip()
                    if t and (not cells or cells[-1] != t):   # merged cells repeat text
                        cells.append(t)
                if cells:
                    lines.append(" | ".join(cells))
            lines.append("")
    return lines


def _heading_of(line: str) -> str | None:
    m = MD_HEADING.match(line)
    if m:
        return m.group(2).strip()
    m = NUM_HEADING.match(line)
    # "4. Data Retention" is a heading; "4.2 Records shall be kept for 3 years." is a clause
    if m and len(line.split()) <= 10 and not line.rstrip().endswith((".", ";", ":")):
        return line.strip()
    return None


def _ref_of(heading: str) -> str | None:
    m = REF_PREFIX.match(heading)
    return m.group(1) if m else None


def chunk_document(lines: list[str], max_words: int = 320, overlap_words: int = 40) -> tuple[str | None, list[Chunk]]:
    """Return (title, chunks). Chunks follow section boundaries and are split if too long."""
    title: str | None = None
    sections: list[tuple[str | None, str, list[str]]] = []
    ref, heading, buf = None, "", []

    def flush():
        if any(x.strip() for x in buf):
            sections.append((ref, heading, list(buf)))

    for raw in lines:
        line = raw.strip()
        h = _heading_of(line) if line else None
        if h:
            if title is None and MD_HEADING.match(line) and line.startswith("# "):
                title = h
            flush()
            ref, heading, buf = _ref_of(h), h, []
        else:
            buf.append(line)
    flush()

    chunks: list[Chunk] = []
    for sref, head, body in sections:
        paragraphs = _paragraphs(body)
        for piece in _pack(paragraphs, max_words, overlap_words):
            # A numbered clause inside the piece is a better reference than the section number
            clause = next((m.group(1) for p in piece.splitlines() if (m := REF_PREFIX.match(p))), None)
            chunks.append(Chunk(len(chunks), clause or sref, head, piece))
    return title, chunks


def _paragraphs(body: list[str]) -> list[str]:
    out, cur = [], []
    for line in body:
        if line:
            cur.append(line)
        elif cur:
            out.append("\n".join(cur))
            cur = []
    if cur:
        out.append("\n".join(cur))
    return out


def _pack(paragraphs: list[str], max_words: int, overlap: int) -> list[str]:
    pieces, cur, count = [], [], 0
    for para in paragraphs:
        words = para.split()
        if len(words) > max_words:  # one giant paragraph: window it
            if cur:
                pieces.append("\n\n".join(cur))
                cur, count = [], 0
            step = max_words - overlap
            for i in range(0, len(words), step):
                pieces.append(" ".join(words[i : i + max_words]))
                if i + max_words >= len(words):
                    break
            continue
        if count + len(words) > max_words and cur:
            pieces.append("\n\n".join(cur))
            cur, count = [], 0
        cur.append(para)
        count += len(words)
    if cur:
        pieces.append("\n\n".join(cur))
    return pieces


def embedding_text(doc_title: str, chunk: Chunk) -> str:
    """Contextual header improves retrieval a lot for short policy clauses."""
    head = f"{doc_title} > {chunk.heading}" if chunk.heading else doc_title
    return f"{head}\n{chunk.content}"
