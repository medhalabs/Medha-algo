"""Chain-derived context: expiry, ATM IV, OI peaks, suggested-strike quote (no DB)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.dhan_fetch import get_leg_at_strike


def iv_display_pct(iv: float | None) -> str:
    if iv is None:
        return "—"
    v = float(iv)
    pct = v * 100 if abs(v) <= 3.0 else v
    return f"{pct:.2f}%"


def expiry_calendar_days(expiry_str: str) -> int | None:
    try:
        d0 = datetime.strptime(expiry_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (d0 - date.today()).days


def expiry_label(expiry_str: str) -> str:
    d = expiry_calendar_days(expiry_str)
    if d is None:
        return "—"
    if d < 0:
        return f"Date passed ({expiry_str[:10]})"
    if d == 0:
        return "Expiry day (0 calendar days left)"
    return f"{d} calendar day(s) to expiry"


def spread_display(leg: dict[str, Any]) -> str:
    b, a = leg.get("bid"), leg.get("ask")
    if b is None or a is None:
        return "—"
    b, a = float(b), float(a)
    if a < b:
        return "—"
    ru = a - b
    mid = (a + b) / 2
    if mid <= 0:
        return f"{ru:.2f}"
    pct = (ru / mid) * 100
    return f"{ru:.2f} ({pct:.1f}% of mid)"


def oi_change_display(leg: dict[str, Any]) -> str:
    oi, po = leg.get("oi"), leg.get("prev_oi")
    if oi is None or po is None:
        return "—"
    d = float(oi) - float(po)
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:,.0f}"


def max_oi_strike_each_side(
    raw_oc: dict[str, Any],
    strikes: list[float],
) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    """((strike, ce_oi), (strike, pe_oi)) with highest OI per side."""
    best_ce: tuple[float, float] | None = None
    best_pe: tuple[float, float] | None = None
    for sk in strikes:
        ce = get_leg_at_strike(raw_oc, float(sk), "ce")
        pe = get_leg_at_strike(raw_oc, float(sk), "pe")
        oic = ce.get("oi")
        oip = pe.get("oi")
        if oic is not None:
            v = float(oic)
            if best_ce is None or v > best_ce[1]:
                best_ce = (float(sk), v)
        if oip is not None:
            v = float(oip)
            if best_pe is None or v > best_pe[1]:
                best_pe = (float(sk), v)
    return best_ce, best_pe


def suggested_leg_snapshot(
    signal: str,
    rec: dict[str, Any],
    raw_oc: dict[str, Any],
) -> dict[str, Any] | None:
    """LTP / IV / Greeks / spread for the strike the scorer picked (CE or PE only)."""
    if signal not in ("BUY_CE", "BUY_PE"):
        return None
    raw = rec.get("strike")
    if raw is None:
        return None
    try:
        strike = float(raw)
    except (TypeError, ValueError):
        return None
    side = "ce" if signal == "BUY_CE" else "pe"
    leg = get_leg_at_strike(raw_oc, strike, side)
    name = "Call (CE)" if side == "ce" else "Put (PE)"
    return {
        "side_name": name,
        "strike": strike,
        "ltp": leg.get("ltp"),
        "iv": iv_display_pct(leg.get("iv")),
        "delta": leg.get("delta"),
        "gamma": leg.get("gamma"),
        "theta": leg.get("theta"),
        "vega": leg.get("vega"),
        "oi": leg.get("oi"),
        "volume": leg.get("volume"),
        "oi_ch": oi_change_display(leg),
        "spread": spread_display(leg),
        "bid": leg.get("bid"),
        "ask": leg.get("ask"),
    }


def atm_iv_pair(raw_oc: dict[str, Any], atm: float) -> tuple[str, str]:
    ce = get_leg_at_strike(raw_oc, atm, "ce")
    pe = get_leg_at_strike(raw_oc, atm, "pe")
    return iv_display_pct(ce.get("iv")), iv_display_pct(pe.get("iv"))


def atm_combined_premium(raw_oc: dict[str, Any], atm: float) -> str | None:
    """ATM CE LTP + PE LTP (quick straddle premium reference)."""
    ce = get_leg_at_strike(raw_oc, atm, "ce")
    pe = get_leg_at_strike(raw_oc, atm, "pe")
    a, b = ce.get("ltp"), pe.get("ltp")
    if a is None or b is None:
        return None
    return f"{float(a) + float(b):,.2f}"
