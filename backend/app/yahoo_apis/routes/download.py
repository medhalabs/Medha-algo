import asyncio

from fastapi import APIRouter, Query

from app.yahoo_apis import service

router = APIRouter()


@router.get("/download", summary="Batch OHLCV (yfinance download)")
async def download_ohlc(
    symbols: str = Query(
        ...,
        description="Comma-separated symbols, e.g. RELIANCE.NS,TCS.NS,^NSEI",
    ),
    period: str | None = Query(None),
    interval: str = Query("1d"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    group_by: str = Query("column"),
    auto_adjust: bool = Query(True),
    threads: bool = Query(True),
):
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    if not syms:
        return {"empty": True, "format": "split", "columns": [], "index": [], "data": []}
    return await asyncio.to_thread(
        service.download_ohlc,
        syms,
        period=period,
        interval=interval,
        start=start,
        end=end,
        group_by=group_by,
        auto_adjust=auto_adjust,
        threads=threads,
    )
