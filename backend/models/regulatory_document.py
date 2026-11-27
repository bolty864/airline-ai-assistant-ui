from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.compliance_obligation import ComplianceObligation


class RegulatoryDocument(Base):
    """Owned by Agent 1. Agent 2 only reads it."""

    __tablename__ = "regulatory_documents"
    __mapper_args__ = {"eager_defaults": True}  # server defaults / NOW() come back via RETURNING

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    regulator: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    blob_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version_tag: Mapped[str | None] = mapped_column(String(50), server_default="v1.0")
    status: Mapped[str | None] = mapped_column(String(30), server_default="ACTIVE")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    obligations: Mapped[list[ComplianceObligation]] = relationship(
        back_populates="document", passive_deletes=True, lazy="raise"
    )
