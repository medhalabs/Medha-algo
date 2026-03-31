import asyncio

from fastapi import APIRouter, Query

from app.yahoo_apis import service

router = APIRouter()


@router.get("/earnings", summary="Earnings calendar (Yahoo)")
async def earnings_calendar(
    start: str | None = Query(None, description="Start date (YYYY-MM-DD or yfinance-accepted string)"),
    end: str | None = Query(None),
    market_cap: float | None = Query(None, description="Optional market cap filter"),
    filter_most_active: bool = Query(True),
    limit: int = Query(12, ge=1, le=500),
    offset: int = Query(0, ge=0),
    force: bool = Query(False, description="Bypass yfinance cache when supported"),
):
    return await asyncio.to_thread(
        service.calendars_earnings,
        start=start,
        end=end,
        market_cap=market_cap,
        filter_most_active=filter_most_active,
        limit=limit,
        offset=offset,
        force=force,
    )


@router.get("/economic-events", summary="Economic events calendar (Yahoo)")
async def economic_events_calendar(
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(12, ge=1, le=500),
    offset: int = Query(0, ge=0),
    force: bool = Query(False),
):
    return await asyncio.to_thread(
        service.calendars_economic_events,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        force=force,
    )


@router.get("/splits", summary="Stock splits calendar (Yahoo)")
async def splits_calendar(
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(12, ge=1, le=500),
    offset: int = Query(0, ge=0),
    force: bool = Query(False),
):
    return await asyncio.to_thread(
        service.calendars_splits,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        force=force,
    )


@router.get("/ipo", summary="IPO calendar (Yahoo)")
async def ipo_calendar(
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(12, ge=1, le=500),
    offset: int = Query(0, ge=0),
    force: bool = Query(False),
):
    return await asyncio.to_thread(
        service.calendars_ipo,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        force=force,
    )
