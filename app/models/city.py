from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
import uuid
from sqlalchemy.dialects.postgresql import UUID


class City(Base):
    """Справочник городов выполнения заказов."""

    __tablename__ = "cities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
