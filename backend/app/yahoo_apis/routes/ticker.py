import asyncio

from fastapi import APIRouter, Query

from app.yahoo_apis import service

router = APIRouter()


@router.get("/{symbol}/info", summary="Ticker info / metadata (Yahoo)")
async def ticker_info(symbol: str):
    return await asyncio.to_thread(service.ticker_info, symbol)


@router.get("/{symbol}/history", summary="OHLCV history")
async def ticker_history(
    symbol: str,
    period: str | None = Query(None, description="e.g. 1d, 5d, 1mo — default 1mo if no start/end"),
    interval: str = Query("1d"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    prepost: bool = Query(False),
    auto_adjust: bool = Query(True),
):
    return await asyncio.to_thread(
        service.ticker_history,
        symbol,
        period=period,
        interval=interval,
        start=start,
        end=end,
        prepost=prepost,
        auto_adjust=auto_adjust,
    )


@router.get("/{symbol}/dividends", summary="Dividend series")
async def ticker_dividends(symbol: str):
    return await asyncio.to_thread(service.ticker_dividends, symbol)


@router.get("/{symbol}/splits", summary="split series")
async def ticker_splits(symbol: str):
    return await asyncio.to_thread(service.ticker_splits, symbol)


@router.get("/{symbol}/actions", summary="Dividends and splits combined")
async def ticker_actions(symbol: str):
    return await asyncio.to_thread(service.ticker_actions, symbol)
