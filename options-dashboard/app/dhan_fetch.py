"""Dhan API helpers (intraday OHLCV, expiry list, option chain)."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from dhanhq import dhanhq
from dotenv import load_dotenv

from app.config import OPTION_CHAIN_MIN_INTERVAL_SEC

load_dotenv()


def get_client() -> dhanhq:
    cid = os.getenv("DHAN_CLIENT_ID", "").strip()
    tok = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    if not cid or not tok:
        raise RuntimeError("Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN in environment or .env")
    return dhanhq(cid, tok)


def _body(resp: dict[str, Any]) -> dict[str, Any]:
    """Unwrap dhanhq `{'status','data': full_http_json}` where HTTP JSON may nest `data` again."""
    if resp.get("status") == "failure":
        raise RuntimeError(f"Dhan API error: {resp.get('remarks', resp)}")
    body = resp.get("data")
    if not isinstance(body, dict):
        raise RuntimeError(f"Unexpected Dhan wrapper: {resp}")
    if "open" in body:
        return body
    inner = body.get("data")
    if isinstance(inner, dict) and "open" in inner:
        return inner
    if "last_price" in body:
        return body
    if isinstance(inner, dict) and "last_price" in inner:
        return inner
    raise RuntimeError(f"Unexpected Dhan response shape: {list(body.keys())}")


def intraday_to_df(raw: dict[str, Any]) -> pd.DataFrame:
    ts = raw.get("timestamp") or raw.get("timestamps")
    if not ts:
        raise RuntimeError("No timestamps in intraday response")
    df = pd.DataFrame(
        {
            "open": raw["open"],
            "high": raw["high"],
            "low": raw["low"],
            "close": raw["close"],
            "volume": raw.get("volume", [0] * len(raw["close"])),
        }
    )
    df["ts"] = pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kolkata")
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def fetch_intraday(
    client: dhanhq,
    security_id: int,
    exchange_segment: str,
    instrument_type: str,
    interval: int,
    days_back: int = 5,
) -> pd.DataFrame:
    """Fetch minute candles (Dhan allows ~5 trading days per request)."""
    end = datetime.now()
    start = end - timedelta(days=days_back)
    fmt = "%Y-%m-%d %H:%M:%S"
    r = client.intraday_minute_data(
        str(security_id),
        exchange_segment,
        instrument_type,
        start.strftime(fmt),
        end.strftime(fmt),
        interval,
    )
    raw = _body(r)
    return intraday_to_df(raw)


_last_chain_ts = 0.0


def _throttle_chain() -> None:
    global _last_chain_ts
    now = time.monotonic()
    wait = OPTION_CHAIN_MIN_INTERVAL_SEC - (now - _last_chain_ts)
    if wait > 0:
        time.sleep(wait)
    _last_chain_ts = time.monotonic()


def fetch_expiry_list(client: dhanhq, under_security_id: int, under_seg: str) -> list[str]:
    _throttle_chain()
    r = client.expiry_list(under_security_id, under_seg)
    if r.get("status") == "failure":
        raise RuntimeError(f"expiry_list: {r.get('remarks', r)}")
    body = r.get("data")
    if isinstance(body, list):
        return [str(x) for x in body]
    if isinstance(body, dict):
        inner = body.get("data")
        if isinstance(inner, list):
            return [str(x) for x in inner]
        if isinstance(inner, dict) and isinstance(inner.get("data"), list):
            return [str(x) for x in inner["data"]]
    raise RuntimeError(f"Unexpected expiry_list payload: {r}")


def pick_next_expiry(expiry_dates: list[str], today: datetime | None = None) -> str:
    """Nearest expiry strictly on or after today (IST)."""
    today = today or datetime.now()
    d0 = today.date()
    parsed: list[tuple[str, Any]] = []
    for e in expiry_dates:
        try:
            parsed.append((e, datetime.strptime(e[:10], "%Y-%m-%d").date()))
        except ValueError:
            continue
    parsed.sort(key=lambda x: x[1])
    for s, dt in parsed:
        if dt >= d0:
            return s
    return parsed[-1][0] if parsed else expiry_dates[0]


def fetch_option_chain(client: dhanhq, under_security_id: int, under_seg: str, expiry: str) -> dict[str, Any]:
    _throttle_chain()
    r = client.option_chain(under_security_id, under_seg, expiry)
    if r.get("status") == "failure":
        raise RuntimeError(f"option_chain: {r.get('remarks', r)}")
    body = r.get("data")
    if not isinstance(body, dict):
        raise RuntimeError(f"Unexpected option_chain payload: {r}")
    if "last_price" in body and "oc" in body:
        return body
    inner = body.get("data")
    if isinstance(inner, dict) and "last_price" in inner:
        return inner
    return body


def strikes_from_chain(oc: dict[str, Any]) -> tuple[float, list[float], dict[str, Any]]:
    """
    Returns (last_price, sorted strikes, raw oc dict).
    `oc` is the inner payload with `last_price` and `oc` keys.
    """
    spot = float(oc.get("last_price") or 0)
    raw_oc = oc.get("oc") or {}
    strikes: list[float] = []
    for k in raw_oc.keys():
        try:
            strikes.append(float(k))
        except (TypeError, ValueError):
            continue
    strikes.sort()
    return spot, strikes, raw_oc


def refresh_bucket(interval_minutes: int) -> int:
    """Time bucket for cache keys so data refetches each candle period."""
    sec = max(60, int(interval_minutes) * 60)
    return int(time.time() // sec)


def _f(x: Any) -> float | None:
    try:
        if x is None:
            return None
        v = float(x)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _leg_data(strike_payload: Any, side: str) -> dict[str, Any]:
    """Normalize CE/PE leg from Dhan `oc[strike]` (keys may be ce/pe or nested)."""
    if not isinstance(strike_payload, dict):
        return {}
    leg: dict[str, Any] | None = None
    for k in (side, side.upper(), side.lower()):
        v = strike_payload.get(k)
        if isinstance(v, dict):
            leg = v
            break
    if leg is None:
        return {}
    g = leg.get("greeks")
    g = g if isinstance(g, dict) else {}
    return {
        "ltp": _f(leg.get("last_price")),
        "oi": _f(leg.get("oi")),
        "volume": _f(leg.get("volume")),
        "iv": _f(leg.get("implied_volatility")),
        "bid": _f(leg.get("top_bid_price")),
        "ask": _f(leg.get("top_ask_price")),
        "bid_qty": _f(leg.get("top_bid_quantity")),
        "ask_qty": _f(leg.get("top_ask_quantity")),
        "prev_oi": _f(leg.get("previous_oi")),
        "delta": _f(g.get("delta")),
        "gamma": _f(g.get("gamma")),
        "theta": _f(g.get("theta")),
        "vega": _f(g.get("vega")),
    }


def option_chain_detail_df(
    raw_oc: dict[str, Any],
    strikes: list[float],
    spot: float,
    *,
    center: int = 17,
    atm_strike: float | None = None,
) -> pd.DataFrame:
    """
    Wide table: strike + CE/PE LTP, OI, vol, IV, delta, bid/ask for strikes around ATM.
    """
    if not strikes:
        return pd.DataFrame()
    atm = atm_strike if atm_strike is not None else min(strikes, key=lambda x: abs(float(x) - spot))
    try:
        idx = strikes.index(atm)
    except ValueError:
        idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
    half = center // 2
    lo = max(0, idx - half)
    hi = min(len(strikes), lo + center)
    if hi - lo < min(center, len(strikes)):
        lo = max(0, hi - center)

    rows: list[dict[str, Any]] = []
    for sk in strikes[lo:hi]:
        payload = strike_payload_for(raw_oc, float(sk))
        ce = _leg_data(payload, "ce")
        pe = _leg_data(payload, "pe")

        def fmt_leg(prefix: str, leg: dict[str, Any]) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for short, val in [
                ("LTP", leg.get("ltp")),
                ("OI", leg.get("oi")),
                ("Vol", leg.get("volume")),
                ("IV %", leg.get("iv")),
                ("Δ", leg.get("delta")),
                ("Bid", leg.get("bid")),
                ("Ask", leg.get("ask")),
                ("Γ", leg.get("gamma")),
                ("Θ", leg.get("theta")),
            ]:
                col = f"{prefix} {short}"
                if val is None:
                    out[col] = None
                elif short == "IV %":
                    v = float(val)
                    pct = v * 100 if abs(v) <= 3.0 else v
                    out[col] = round(pct, 2)
                elif short in ("OI", "Vol"):
                    out[col] = int(round(float(val))) if val is not None else None
                else:
                    fv = float(val)
                    out[col] = round(fv, 4) if abs(fv) < 1e8 else fv
            return out

        row: dict[str, Any] = {"Strike": float(sk)}
        row.update(fmt_leg("CE", ce))
        row.update(fmt_leg("PE", pe))
        rows.append(row)
    return pd.DataFrame(rows)


def strike_payload_for(raw_oc: dict[str, Any], strike: float) -> dict[str, Any]:
    """Return `oc[strike]` dict for a numeric strike (handles string key variants)."""
    if not raw_oc:
        return {}
    key = None
    for candidate in (str(strike), str(int(strike)) if strike == int(strike) else None):
        if candidate is not None and candidate in raw_oc:
            key = candidate
            break
    if key is None:
        for k in raw_oc.keys():
            try:
                if abs(float(k) - float(strike)) < 1e-6:
                    key = k
                    break
            except (TypeError, ValueError):
                continue
    p = raw_oc.get(key, {}) if key is not None else {}
    return p if isinstance(p, dict) else {}


def get_leg_at_strike(raw_oc: dict[str, Any], strike: float, side: str) -> dict[str, Any]:
    """CE or PE leg at strike (normalized fields via `_leg_data`)."""
    return _leg_data(strike_payload_for(raw_oc, strike), side)


def chain_oi_summary(raw_oc: dict[str, Any], strikes: list[float]) -> dict[str, float | int]:
    """Totals across all strikes in chain (for PCR-style context)."""
    t_ce = t_pe = 0.0
    v_ce = v_pe = 0.0
    for sk in strikes:
        payload = strike_payload_for(raw_oc, float(sk))
        ce = _leg_data(payload, "ce")
        pe = _leg_data(payload, "pe")
        if ce.get("oi") is not None:
            t_ce += float(ce["oi"])
        if pe.get("oi") is not None:
            t_pe += float(pe["oi"])
        if ce.get("volume") is not None:
            v_ce += float(ce["volume"])
        if pe.get("volume") is not None:
            v_pe += float(pe["volume"])
    pcr = (t_pe / t_ce) if t_ce > 0 else float("nan")
    return {
        "total_ce_oi": t_ce,
        "total_pe_oi": t_pe,
        "pcr_oi": pcr,
        "total_ce_vol": v_ce,
        "total_pe_vol": v_pe,
        "strikes_count": len(strikes),
    }
