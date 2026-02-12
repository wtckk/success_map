from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

import uuid
from sqlalchemy.dialects.postgresql import UUID


class TaskReport(Base):
    """Отчет по заданию (фото + аккаунт)."""

    __tablename__ = "task_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_assignments.id"), unique=True
    )

    account_name: Mapped[str] = mapped_column(String(128))
    photo_file_id: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=uuid.uuid4,
    )
