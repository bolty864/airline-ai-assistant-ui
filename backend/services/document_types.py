from __future__ import annotations

from dataclasses import dataclass, field


class DocumentParseError(Exception):
    """Raised when a document cannot be turned into usable text."""


@dataclass
class ParsedDocument:
    text: str
    format: str                      # pdf | docx | html
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text)
