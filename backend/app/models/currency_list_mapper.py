from datetime import datetime
from sqlalchemy import BigInteger, String, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

class CurrencyListMapper(Base):
    __tablename__ = "currency_list_mapper"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    currency_name: Mapped[str] = mapped_column(String(100), nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "currency_code",
            name="uq_currency_list_mapper_currency_code",
        ),
    )
    