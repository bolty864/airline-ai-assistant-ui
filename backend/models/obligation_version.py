from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.compliance_obligation import EMBEDDING_DIMS


class ObligationVersion(Base):
    """Obligations of a previous version of a regulatory document (written by Agent 2 just before it replaces them)."""

    __tablename__ = "regulation_obligation_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("regulatory_documents.id", ondelete="CASCADE"), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    clause_ref: Mapped[str | None] = mapped_column(String(100))
    obligation_text: Mapped[str] = mapped_column(Text, nullable=False)
    obligation_type: Mapped[str | None] = mapped_column(String(100))
    owner_function: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str | None] = mapped_column(String(20))
    target_system: Mapped[str | None] = mapped_column(String(100))
    citation: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMS))
    mapped_assets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    superseded_by_hash: Mapped[str | None] = mapped_column(String(64))
    superseded_by_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
