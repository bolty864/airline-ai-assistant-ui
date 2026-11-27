from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class RegulationChangeImpact(Base):
    """One detected change between the previous and the new version of a regulation."""

    __tablename__ = "regulation_change_impacts"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("regulatory_documents.id", ondelete="CASCADE"), nullable=False)
    change_type: Mapped[str] = mapped_column(String(100), nullable=False)
    old_clause: Mapped[str | None] = mapped_column(Text)
    new_clause: Mapped[str | None] = mapped_column(Text)
    affected_control: Mapped[str | None] = mapped_column(Text)
    affected_system: Mapped[str | None] = mapped_column(Text)
    affected_team: Mapped[str | None] = mapped_column(Text)
    risk_rating: Mapped[str] = mapped_column(String(20), nullable=False)
    remediation_action: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    impact_key: Mapped[str] = mapped_column(String(32), nullable=False)
    clause_ref: Mapped[str | None] = mapped_column(String(100))
    new_obligation_id: Mapped[int | None] = mapped_column(ForeignKey("compliance_obligations.id", ondelete="SET NULL"))
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    summary: Mapped[str | None] = mapped_column(Text)
    additional_changes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    affected_controls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    affected_systems: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    affected_teams: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    model_used: Mapped[str | None] = mapped_column(String(100))


class RegulationImpactRun(Base):
    """Overall result of the last analysis of a document."""

    __tablename__ = "regulation_impact_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("regulatory_documents.id", ondelete="CASCADE"), unique=True,
                                             nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    baseline: Mapped[str | None] = mapped_column(String(200))
    previous_version: Mapped[str | None] = mapped_column(String(50))
    current_version: Mapped[str | None] = mapped_column(String(50))
    total_changes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    by_change_type: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    by_risk: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    overall_risk_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    overall_risk_rating: Mapped[str | None] = mapped_column(String(20))
    summary: Mapped[str | None] = mapped_column(Text)
    pending_mapping: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, server_default=text("'{}'"))
    model_used: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
