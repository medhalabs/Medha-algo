"""
Example: insert one row into dhan_yahoo_instrument_map.

Run from repo root:
  uv run --directory backend python scripts/insert_mapping_example.py

Or from backend/:
  uv run python scripts/insert_mapping_example.py

Requires backend/.env with DATABASE_URL. Fails if the row already exists (unique constraint).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure backend is on path when run as script
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import close_db, get_session_factory  # noqa: E402
from app.models.dhan_yahoo_map import DhanYahooInstrumentMap  # noqa: E402


async def main() -> None:
    get_settings()
    factory = get_session_factory()
    async with factory() as session:
        row = DhanYahooInstrumentMap(
            dhan_exch_id="NSE",
            dhan_segment="E",
            dhan_underlying_symbol="INFY",
            dhan_symbol_name="INFOSYS LIMITED",
            dhan_display_name="Infosys",
            dhan_security_id=1594,
            isin="INE009A01021",
            yahoo_symbol="INFY.NS",
            mapping_source="example_script",
        )
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            print(
                "Skip: row already exists (duplicate dhan_security_id or natural key).",
                file=sys.stderr,
            )
            return
        await session.refresh(row)
        print(f"Inserted row id={row.id} yahoo_symbol={row.yahoo_symbol}")
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
