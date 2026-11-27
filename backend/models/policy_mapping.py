"""Read-only mirrors of the tables Agent 3 owns (created by sql/002). Agent 4 never writes to them."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ObligationMapping(Base):
    """Agent 3 output: obligation -> policy section / control / system."""

    __tablename__ = "obligation_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    obligation_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)      # POLICY_SECTION | CONTROL | SYSTEM
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_code: Mapped[str] = mapped_column(String(200), nullable=False)
    target_doc_code: Mapped[str | None] = mapped_column(String(100))
    link_type: Mapped[str] = mapped_column(String(20), nullable=False)        # DIRECT | SUPPORTING | CONTEXTUAL
    relevance_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)   # 0-100, "is it impacted"
    current_provision: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str | None] = mapped_column(String(20))             # PROPOSED | CONFIRMED | REJECTED


class Control(Base):
    __tablename__ = "controls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    control_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    control_type: Mapped[str | None] = mapped_column(String(50))
    owner_function: Mapped[str | None] = mapped_column(String(100))
    frequency: Mapped[str | None] = mapped_column(String(50))
    policy_doc_code: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str | None] = mapped_column(String(30))
    automation_level: Mapped[str | None] = mapped_column(String(20))
    evidence_source: Mapped[str | None] = mapped_column(Text)
    last_evidence_at: Mapped[datetime | None] = mapped_column(DateTime)
    test_result: Mapped[str | None] = mapped_column(String(20))


class System(Base):
    __tablename__ = "systems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    system_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    data_categories: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    owner_function: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str | None] = mapped_column(String(30))
    criticality: Mapped[str | None] = mapped_column(String(20))      # CRITICAL | HIGH | MEDIUM | LOW


class EnterpriseDocument(Base):
    __tablename__ = "enterprise_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_code: Mapped[str] = mapped_column(String(100), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    version_tag: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str | None] = mapped_column(String(30))


class EnterpriseChunk(Base):
    __tablename__ = "enterprise_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    section_ref: Mapped[str | None] = mapped_column(String(50))
    heading: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
