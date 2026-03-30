"""Map Dhan instrument identifiers to Yahoo Finance (yfinance) symbols."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DhanYahooInstrumentMap(Base):
    """
    Cross-provider mapping for pipelines that fetch Dhan vs Yahoo data for the same instrument.

    Dhan (CSV / API) uses numeric SECURITY_ID, EXCH_ID (NSE/BSE), UNDERLYING_SYMBOL, names.
    Yahoo uses symbols like ``INFY.NS`` (NSE) or ``INFY.BO`` (BSE).

    Natural key for equities: (dhan_exch_id, dhan_segment, dhan_underlying_symbol) — one row per
    exchange listing; ``dhan_security_id`` is optional but unique when set for direct Dhan API calls.
    """

    __tablename__ = "dhan_yahoo_instrument_map"
    __table_args__ = (
        UniqueConstraint(
            "dhan_exch_id",
            "dhan_segment",
            "dhan_underlying_symbol",
            name="uq_dhan_yahoo_dhan_symbol_exch_seg",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    dhan_security_id: Mapped[int | None] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=True,
        doc="Dhan SECURITY_ID from instrument master (nullable if not resolved yet)",
    )
    isin: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)

    dhan_exch_id: Mapped[str] = mapped_column(String(8), index=True)
    dhan_segment: Mapped[str] = mapped_column(String(16), default="", server_default=text("''"))
    dhan_underlying_symbol: Mapped[str] = mapped_column(String(128), index=True)
    dhan_symbol_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    dhan_display_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    yahoo_symbol: Mapped[str] = mapped_column(String(64), index=True)
    mapping_source: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="manual | rule_nse_suffix | csv_import | script",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )
