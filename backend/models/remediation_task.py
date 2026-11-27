from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class RemediationTask(Base):
    __tablename__ = "remediation_tasks"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    impact_id: Mapped[int] = mapped_column(ForeignKey("regulation_change_impacts.id", ondelete="CASCADE"), nullable=False)
    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    owner_team: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[str | None] = mapped_column(String(20))
    due_days: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(20), server_default="OPEN")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    task_key: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
