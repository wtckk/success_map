import uuid
from datetime import datetime, UTC

from sqlalchemy import String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Task(Base):
    """Шаблон задания, создаваемый администраторами."""

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    example_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=True,  # "2ГИС"/"Яндекс Карты"/"Google maps"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(UTC), server_default=func.now()
    )

    link: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    required_gender: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # "M"/"F"/None

    city_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cities.id"),
        nullable=True,
    )

    city = relationship("City")
