from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AppMetadata(Base):
    """Minimal table so Alembic and Postgres connectivity have a real schema."""

    __tablename__ = "app_metadata"

    key: Mapped[str] = mapped_column(String(256), primary_key=True)
    value: Mapped[str | None] = mapped_column(String(4096), nullable=True)
