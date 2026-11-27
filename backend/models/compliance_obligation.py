from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.regulatory_document import RegulatoryDocument

EMBEDDING_DIMS = 1536


class ComplianceObligation(Base):
    """Written by Agent 2; mapping_* columns are maintained by Agent 3."""

    __tablename__ = "compliance_obligations"
    __mapper_args__ = {"eager_defaults": True}  # fetch id/created_at/mapping_status via RETURNING

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("regulatory_documents.id", ondelete="CASCADE"))
    clause_ref: Mapped[str | None] = mapped_column(String(100))
    obligation_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_system: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str | None] = mapped_column(String(20))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMS))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    obligation_type: Mapped[str | None] = mapped_column(String(100))
    owner_function: Mapped[str | None] = mapped_column(String(100))
    citation: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # 0-100

    # Agent 3 work queue (new rows start as PENDING)
    mapping_status: Mapped[str | None] = mapped_column(String(20), server_default="PENDING")
    mapped_at: Mapped[datetime | None] = mapped_column(DateTime)
    mapping_model: Mapped[str | None] = mapped_column(String(100))

    document: Mapped[RegulatoryDocument] = relationship(back_populates="obligations", lazy="raise")
