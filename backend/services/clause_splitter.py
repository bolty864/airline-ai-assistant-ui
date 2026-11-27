"""Split regulatory text into numbered clauses.

Handles DGCA CAR / BCAS AvSec / CERT-In / DPDP styles:
  "4.2 Passenger API records shall ..."      numeric clauses (1, 4.2, 4.2.1)
  "Para 4.1", "Section 3", "Rule 8", "Article 5", "Regulation 12"
  "(a) ...", "(ii) ..."                       sub-clauses (kept with parent, split only if too long)
Short un-punctuated numbered lines ("4. DATA RETENTION") are treated as headings and passed
as context. Documents without numbering fall back to paragraph chunks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from services.obligation_rules import has_mandatory_language
from services.text_utils import sentences

_KEYWORD_START = re.compile(
    r"^(?:section|clause|para(?:graph)?|rule|regulation|article)\s+(\d{1,3}[A-Z]?(?:\.\d{1,3}){0,4})\s*[.:)\-–]?\s*",
    re.I,
)
_NUMERIC_START = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){0,4})[.)]?\s+(?=[A-Z(\"'“])")
_SUB_START = re.compile(r"^\(?([a-z]|[ivx]{1,5})\)\s+", re.I)
_TOC_LINE = re.compile(r"(\.{4,}|…{2,}|\s{3,})\s*\d{1,4}\s*$")


@dataclass
class Clause:
    clause_number: str
    text: str
    heading: str = ""

    @property
    def is_candidate(self) -> bool:
        """Only clauses with mandatory language go to the LLM."""
        return has_mandatory_language(self.text)


class ClauseSplitter:
    def __init__(self, max_clause_chars: int = 6000, fallback_chunk_chars: int = 1500):
        self.max_chars = max_clause_chars
        self.fallback_chars = fallback_chunk_chars

    def split(self, text: str) -> list[Clause]:
        lines = [ln.strip() for ln in text.splitlines()]
        lines = [ln for ln in lines if not _TOC_LINE.search(ln)]

        raw: list[Clause] = []
        number, heading, buf = "PREAMBLE", "", []
        found_numbering = False

        def flush() -> None:
            body = "\n".join(buf).strip()
            if body:
                raw.append(Clause(number, body, heading))

        for line in lines:
            if not line:
                buf.append("")
                continue
            ref, rest = self._clause_start(line)
            if ref is None:
                buf.append(line)
                continue
            found_numbering = True
            if self._is_heading(rest):
                flush()
                number, heading, buf = ref, rest or line, []
                continue
            flush()
            number, buf = ref, [line]
        flush()

        if not found_numbering:
            return self._paragraph_chunks(text)

        out: list[Clause] = []
        for c in raw:
            out.extend(self._split_long(c) if len(c.text) > self.max_chars else [c])
        return self._dedupe_numbers(out)

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _clause_start(line: str) -> tuple[str | None, str]:
        m = _KEYWORD_START.match(line)
        if m:
            return m.group(1), line[m.end():].strip()
        m = _NUMERIC_START.match(line)
        if m:
            return m.group(1), line[m.end():].strip()
        return None, line

    @staticmethod
    def _is_heading(rest: str) -> bool:
        if not rest:
            return True
        words = rest.split()
        return len(words) <= 10 and not rest.endswith((".", ";", ":")) and not has_mandatory_language(rest)

    def _split_long(self, clause: Clause) -> list[Clause]:
        """Split an oversized clause at (a)/(i) markers, prefixing the parent's lead-in for context."""
        lines = clause.text.splitlines()
        stem, parts, cur_ref, cur = [], [], None, []
        for line in lines:
            m = _SUB_START.match(line)
            if m:
                if cur_ref is not None:
                    parts.append((cur_ref, cur))
                cur_ref, cur = m.group(1), [line]
            elif cur_ref is None:
                stem.append(line)
            else:
                cur.append(line)
        if cur_ref is not None:
            parts.append((cur_ref, cur))

        if not parts:
            return self._window(clause)
        lead = " ".join(stem).strip()
        out = []
        if lead and has_mandatory_language(lead):
            out.append(Clause(clause.clause_number, lead, clause.heading))
        for ref, body in parts:
            text = (lead + "\n" if lead else "") + "\n".join(body)
            sub = Clause(f"{clause.clause_number}({ref})", text, clause.heading)
            out.extend(self._window(sub) if len(text) > self.max_chars else [sub])
        return out

    def _window(self, clause: Clause) -> list[Clause]:
        chunks, cur = [], ""
        for s in sentences(clause.text):
            if cur and len(cur) + len(s) > self.max_chars:
                chunks.append(cur)
                cur = ""
            cur = f"{cur} {s}".strip()
        if cur:
            chunks.append(cur)
        if len(chunks) == 1:
            return [clause]
        return [Clause(f"{clause.clause_number}-part{i}", c, clause.heading) for i, c in enumerate(chunks, 1)]

    def _paragraph_chunks(self, text: str) -> list[Clause]:
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        out, cur = [], ""
        for p in paras:
            if cur and len(cur) + len(p) > self.fallback_chars:
                out.append(cur)
                cur = ""
            cur = f"{cur}\n\n{p}".strip()
        if cur:
            out.append(cur)
        clauses: list[Clause] = []
        for i, chunk in enumerate(out, 1):
            c = Clause(f"Para-{i}", chunk)
            clauses.extend(self._window(c) if len(chunk) > self.max_chars else [c])
        return clauses

    @staticmethod
    def _dedupe_numbers(clauses: list[Clause]) -> list[Clause]:
        """Repeated numbers (e.g. annexures restarting at 1) get a suffix so clause refs stay unique."""
        seen: dict[str, int] = {}
        for c in clauses:
            n = seen.get(c.clause_number, 0)
            seen[c.clause_number] = n + 1
            if n:
                c.clause_number = f"{c.clause_number}#{n + 1}"
        return clauses
