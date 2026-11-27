from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.compliance_obligation import EMBEDDING_DIMS


class EmbeddingCache(Base):
    """Shared by Agent 2 and Agent 3: identical text is embedded once."""

    __tablename__ = "embedding_cache"

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(100), primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
