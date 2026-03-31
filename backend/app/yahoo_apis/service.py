"""Blocking yfinance calls — use from routes via asyncio.to_thread."""

from __future__ import annotations

import json
from typing import Any

import yfinance as yf
from fastapi.encoders import jsonable_encoder


def ticker_info(symbol: str) -> dict[str, Any]:
    t = yf.Ticker(symbol)
    info = t.info
    if not info:
        return {}
    return jsonable_encoder(info)


def ticker_history(
    symbol: str,
    *,
    period: str | None = "1mo",
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
    prepost: bool = False,
    auto_adjust: bool = True,
) -> list[dict[str, Any]]:
    t = yf.Ticker(symbol)
    kwargs: dict[str, Any] = {
        "interval": interval,
        "prepost": prepost,
        "auto_adjust": auto_adjust,
    }
    if start or end:
        if start:
            kwargs["start"] = start
        if end:
            kwargs["end"] = end
    else:
        kwargs["period"] = period or "1mo"

    df = t.history(**kwargs)
    if df.empty:
        return []
    out = df.reset_index()
    return jsonable_encoder(out.to_dict(orient="records"))


def ticker_dividends(symbol: str) -> list[dict[str, Any]]:
    t = yf.Ticker(symbol)
    s = t.dividends
    if s is None or len(s) == 0:
        return []
    return jsonable_encoder(s.reset_index().to_dict(orient="records"))


def ticker_splits(symbol: str) -> list[dict[str, Any]]:
    t = yf.Ticker(symbol)
    s = t.splits
    if s is None or len(s) == 0:
        return []
    return jsonable_encoder(s.reset_index().to_dict(orient="records"))


def ticker_actions(symbol: str) -> list[dict[str, Any]]:
    t = yf.Ticker(symbol)
    df = t.actions
    if df is None or df.empty:
        return []
    return jsonable_encoder(df.reset_index().to_dict(orient="records"))


def download_ohlc(
    symbols: list[str],
    *,
    period: str | None = None,
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
    group_by: str = "column",
    auto_adjust: bool = True,
    threads: bool = True,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "interval": interval,
        "group_by": group_by,
        "auto_adjust": auto_adjust,
        "threads": threads,
        "progress": False,
    }
    if start or end:
        if start:
            kwargs["start"] = start
        if end:
            kwargs["end"] = end
    else:
        kwargs["period"] = period or "1mo"

    df = yf.download(symbols, **kwargs)
    if df is None or df.empty:
        return {"empty": True, "format": "split", "columns": [], "index": [], "data": []}

    payload = json.loads(df.to_json(orient="split", date_format="iso"))
    return {"empty": False, "format": "split", **payload}


def search_symbols(query: str, *, max_results: int = 25) -> list[dict[str, Any]]:
    s = yf.Search(query)
    quotes = getattr(s, "quotes", None) or []
    return jsonable_encoder(quotes[: max(1, max_results)])


def _calendar_df_to_records(df: Any) -> list[dict[str, Any]]:
    if df is None or getattr(df, "empty", True):
        return []
    # pandas NaN is not JSON-serializable via jsonable_encoder; to_json maps NaN → null
    raw = df.reset_index().to_json(orient="records", date_format="iso")
    return json.loads(raw)


def calendars_earnings(
    *,
    start: str | None = None,
    end: str | None = None,
    market_cap: float | None = None,
    filter_most_active: bool = True,
    limit: int = 12,
    offset: int = 0,
    force: bool = False,
) -> list[dict[str, Any]]:
    cal = yf.Calendars()
    df = cal.get_earnings_calendar(
        market_cap=market_cap,
        filter_most_active=filter_most_active,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        force=force,
    )
    return _calendar_df_to_records(df)


def calendars_economic_events(
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = 12,
    offset: int = 0,
    force: bool = False,
) -> list[dict[str, Any]]:
    cal = yf.Calendars()
    df = cal.get_economic_events_calendar(
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        force=force,
    )
    return _calendar_df_to_records(df)


def calendars_splits(
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = 12,
    offset: int = 0,
    force: bool = False,
) -> list[dict[str, Any]]:
    cal = yf.Calendars()
    df = cal.get_splits_calendar(
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        force=force,
    )
    return _calendar_df_to_records(df)


def calendars_ipo(
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = 12,
    offset: int = 0,
    force: bool = False,
) -> list[dict[str, Any]]:
    cal = yf.Calendars()
    df = cal.get_ipo_info_calendar(
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        force=force,
    )
    return _calendar_df_to_records(df)
