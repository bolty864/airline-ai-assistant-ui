"""Text helpers shared by Agent 2 and Agent 3 (same normalisation => shared embedding cache hits)."""
from __future__ import annotations

import hashlib
import re

MAX_EMBED_CHARS = 24_000  # ~6k tokens, under the 8k input limit of text-embedding-3-small


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:MAX_EMBED_CHARS]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def loose(text: str) -> str:
    """Lowercase alphanumerics only, used for verbatim checks that ignore punctuation/spacing."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


_SENTENCE_RE = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\"'0-9])")


def sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text).strip()
    return [s.strip() for s in _SENTENCE_RE.split(flat) if s.strip()]
