"""
Fetch Yahoo Finance calendar data via yfinance and upsert into the per-kind tables
(``yahoo_calendar_earnings``, ``yahoo_calendar_economic_events``, ``yahoo_calendar_splits``, ``yahoo_calendar_ipo``).

For each selected calendar type, deletes existing rows for the same (window_start, window_end)
then inserts the fresh fetch (idempotent daily refresh for that window).

Run from repo root:
  uv run --directory backend python scripts/sync_yahoo_calendar_to_db.py
  uv run --directory backend python scripts/sync_yahoo_calendar_to_db.py --calendar-type earnings

Or from ``backend/``:
  uv run python scripts/sync_yahoo_calendar_to_db.py -t economic_events

Requires ``backend/.env`` with ``DATABASE_URL`` and the same settings as the API (e.g. Dhan keys).

Environment (optional):
  MEDHA_CALENDAR_TZ — IANA timezone for "today" (default ``Asia/Kolkata``).
  MEDHA_CALENDAR_DAYS — end date = today + N days (default ``14``).
  MEDHA_CALENDAR_LIMIT — yfinance ``limit`` per request (default ``500``).
  MEDHA_CALENDAR_FORCE — ``1`` to pass ``force=True`` to yfinance (bypass cache when supported).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Ensure backend is on path when run as script
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import delete  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import close_db, get_session_factory  # noqa: E402
from app.models.yahoo_calendar import (  # noqa: E402
    CALENDAR_MODELS,
    CALENDAR_TYPES,
)
from app.yahoo_apis import service  # noqa: E402


def _today_and_end() -> tuple[date, date]:
    tz_name = os.environ.get("MEDHA_CALENDAR_TZ", "Asia/Kolkata")
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()
    days = int(os.environ.get("MEDHA_CALENDAR_DAYS", "14") or "14")
    end = today + timedelta(days=max(0, days))
    return today, end


def _force() -> bool:
    return os.environ.get("MEDHA_CALENDAR_FORCE", "").lower() in ("1", "true", "yes")


def _limit() -> int:
    return max(1, int(os.environ.get("MEDHA_CALENDAR_LIMIT", "500") or "500"))


def _fetch_rows(
    calendar_type: str,
    *,
    start_s: str,
    end_s: str,
    limit: int,
    offset: int,
    force: bool,
) -> tuple[list[dict], dict | None]:
    if calendar_type == "earnings":
        fp = {"market_cap": None, "filter_most_active": True, "force": force}
        rows = service.calendars_earnings(
            start=start_s,
            end=end_s,
            market_cap=None,
            filter_most_active=True,
            limit=limit,
            offset=offset,
            force=force,
        )
        return rows, fp
    if calendar_type == "economic_events":
        fp = {"force": force}
        rows = service.calendars_economic_events(
            start=start_s, end=end_s, limit=limit, offset=offset, force=force
        )
        return rows, fp
    if calendar_type == "splits":
        fp = {"force": force}
        rows = service.calendars_splits(
            start=start_s, end=end_s, limit=limit, offset=offset, force=force
        )
        return rows, fp
    if calendar_type == "ipo":
        fp = {"force": force}
        rows = service.calendars_ipo(
            start=start_s, end=end_s, limit=limit, offset=offset, force=force
        )
        return rows, fp
    raise ValueError(f"unknown calendar_type: {calendar_type!r}")


async def _replace_type(
    session,
    *,
    calendar_type: str,
    window_start: date,
    window_end: date,
    limit: int,
    offset: int,
    rows: list[dict],
    fetch_params: dict | None,
) -> int:
    model = CALENDAR_MODELS[calendar_type]
    await session.execute(
        delete(model).where(
            model.window_start == window_start,
            model.window_end == window_end,
        )
    )
    n = 0
    for row in rows:
        session.add(
            model(
                window_start=window_start,
                window_end=window_end,
                limit_applied=limit,
                offset_applied=offset,
                fetch_params=fetch_params,
                row_data=row,
            )
        )
        n += 1
    await session.commit()
    return n


async def sync_calendar_types(calendar_types: list[str]) -> None:
    get_settings()
    today, window_end = _today_and_end()
    start_s = today.isoformat()
    end_s = window_end.isoformat()
    limit = _limit()
    offset = 0
    force = _force()

    factory = get_session_factory()
    async with factory() as session:
        for calendar_type in calendar_types:
            rows, fp = _fetch_rows(
                calendar_type,
                start_s=start_s,
                end_s=end_s,
                limit=limit,
                offset=offset,
                force=force,
            )
            n = await _replace_type(
                session,
                calendar_type=calendar_type,
                window_start=today,
                window_end=window_end,
                limit=limit,
                offset=offset,
                rows=rows,
                fetch_params=fp,
            )
            print(
                f"{calendar_type}: inserted {n} rows "
                f"(window {start_s}..{end_s})"
            )

    await close_db()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sync Yahoo calendar rows into yahoo_calendar_* tables.",
    )
    p.add_argument(
        "-t",
        "--calendar-type",
        dest="calendar_type",
        choices=["all", *CALENDAR_TYPES],
        default="all",
        help="Which calendar to sync (default: all four).",
    )
    return p.parse_args()


async def main() -> None:
    args = _parse_args()
    if args.calendar_type == "all":
        types_to_run = list(CALENDAR_TYPES)
    else:
        types_to_run = [args.calendar_type]
    await sync_calendar_types(types_to_run)


if __name__ == "__main__":
    asyncio.run(main())
