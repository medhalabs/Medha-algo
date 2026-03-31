"""Persisted Yahoo Finance calendar rows (yfinance Calendars API) — one table per calendar kind."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

CALENDAR_TYPES = ("earnings", "economic_events", "splits", "ipo")


class YahooCalendarRowBase(Base):
    """Shared columns for a fetched calendar window (one row per API row)."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    window_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    window_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    limit_applied: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offset_applied: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetch_params: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Extra query kwargs (e.g. market_cap, filter_most_active, force) as JSON.",
    )
    row_data: Mapped[dict[str, Any]] = mapped_column(JSONB, doc="Single calendar row from Yahoo.")

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )


class YahooCalendarEarnings(YahooCalendarRowBase):
    __tablename__ = "yahoo_calendar_earnings"


class YahooCalendarEconomicEvents(YahooCalendarRowBase):
    __tablename__ = "yahoo_calendar_economic_events"


class YahooCalendarSplits(YahooCalendarRowBase):
    __tablename__ = "yahoo_calendar_splits"


class YahooCalendarIpo(YahooCalendarRowBase):
    __tablename__ = "yahoo_calendar_ipo"


CALENDAR_MODELS: dict[str, type[YahooCalendarRowBase]] = {
    "earnings": YahooCalendarEarnings,
    "economic_events": YahooCalendarEconomicEvents,
    "splits": YahooCalendarSplits,
    "ipo": YahooCalendarIpo,
}
