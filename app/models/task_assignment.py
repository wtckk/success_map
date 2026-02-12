from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

import uuid
from sqlalchemy.dialects.postgresql import UUID


class TaskAssignmentStatus:
    """Статусы выданного задания."""

    ASSIGNED = "ASSIGNED"  # выдано пользователю
    SUBMITTED = "SUBMITTED"  # пользователь отправил отчет
    APPROVED = "APPROVED"  # подтверждено админом
    REJECTED = "REJECTED"  # отклонено админом


class TaskAssignment(Base):
    """Выданное пользователю задание (заказ)."""

    __tablename__ = "task_assignments"

    __table_args__ = (
        Index(
            "ux_task_assignments_task_active",
            "task_id",
            unique=True,
            postgresql_where=(mapped_column("is_archived") == False),  # noqa: E712
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), index=True
    )

    status: Mapped[str] = mapped_column(
        String(32), default=TaskAssignmentStatus.ASSIGNED, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processed_by_admin_id: Mapped[int | None] = mapped_column(
        nullable=True,
        index=True,
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    report_message_id: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    is_archived: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
        index=True,
    )

    user = relationship("User")
    task = relationship("Task")
