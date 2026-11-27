from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ComplianceGapAssessment(Base):
    """One assessment per obligation (re-analysis updates it in place)."""

    __tablename__ = "compliance_gap_assessments"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    obligation_id: Mapped[int] = mapped_column(
        ForeignKey("compliance_obligations.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    mapping_id: Mapped[int | None] = mapped_column(ForeignKey("obligation_mappings.id", ondelete="SET NULL"))
    gap_type: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_rating: Mapped[str] = mapped_column(String(20), nullable=False)
    coverage_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    observation: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    owner_function: Mapped[str | None] = mapped_column(String(100))
    additional_gaps: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    input_fingerprint: Mapped[str | None] = mapped_column(String(64))
    source_mapped_at: Mapped[datetime | None] = mapped_column(DateTime)
    model_used: Mapped[str | None] = mapped_column(String(100))
