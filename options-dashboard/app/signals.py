"""Map indicator readings to 0–10 bullish scores, aggregate signal, strike selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app import indicators as ind


def _clip_score(x: float) -> float:
    return float(np.clip(x, 0.0, 10.0))


def _score_rsi(rsi_v: float) -> tuple[float, str]:
    if np.isnan(rsi_v):
        return 5.0, "N/A"
    if rsi_v >= 70:
        s = 3.0
        note = f"Overbought ({rsi_v:.1f})"
    elif rsi_v <= 30:
        s = 7.0
        note = f"Oversold ({rsi_v:.1f})"
    elif rsi_v >= 55:
        s = 6.5
        note = f"Bullish zone ({rsi_v:.1f})"
    elif rsi_v <= 45:
        s = 3.5
        note = f"Bearish zone ({rsi_v:.1f})"
    else:
        s = 5.0
        note = f"Neutral ({rsi_v:.1f})"
    return _clip_score(s), note


def _score_macd(line: float, sig: float, hist: float) -> tuple[float, str]:
    if any(np.isnan([line, sig, hist])):
        return 5.0, "N/A"
    if line > sig and hist > 0:
        return 7.5, f"Above signal, hist +ve (line {line:.3f} > sig {sig:.3f})"
    if line < sig and hist < 0:
        return 2.5, f"Below signal, hist -ve (line {line:.3f} < sig {sig:.3f})"
    if line > sig:
        return 6.0, f"Above signal ({line:.3f} > {sig:.3f})"
    return 4.0, f"Below signal ({line:.3f} < {sig:.3f})"


def _score_vwap(close: float, vw: float) -> tuple[float, str]:
    if np.isnan(vw) or np.isnan(close):
        return 5.0, "N/A"
    if close > vw * 1.001:
        return 6.5, f"Price above VWAP ({close:.2f} > {vw:.2f})"
    if close < vw * 0.999:
        return 3.5, f"Price below VWAP ({close:.2f} < {vw:.2f})"
    return 5.0, f"At VWAP ({close:.2f} ≈ {vw:.2f})"


def _score_volume_ratio(ratio: float) -> tuple[float, str]:
    if np.isnan(ratio):
        return 5.0, "N/A"
    if ratio >= 1.4:
        return 6.5, f"Volume surge (vol / avg = {ratio:.2f})"
    if ratio <= 0.7:
        return 4.0, f"Below-average volume ({ratio:.2f})"
    return 5.0, f"Normal volume ({ratio:.2f})"


def _score_ema_cross(ema9: float, ema21: float) -> tuple[float, str]:
    if np.isnan(ema9) or np.isnan(ema21):
        return 5.0, "N/A"
    if ema9 > ema21 * 1.0001:
        return 7.0, f"EMA9 > EMA21 ({ema9:.2f} > {ema21:.2f}) uptrend"
    if ema9 < ema21 * 0.9999:
        return 3.0, f"EMA9 < EMA21 ({ema9:.2f} < {ema21:.2f}) downtrend"
    return 5.0, "EMAs flat"


def _score_ema50(close: float, ema50: float) -> tuple[float, str]:
    if np.isnan(close) or np.isnan(ema50):
        return 5.0, "N/A"
    if close > ema50 * 1.001:
        return 6.5, f"Price above EMA50 ({close:.2f} > {ema50:.2f})"
    if close < ema50 * 0.999:
        return 3.5, f"Price below EMA50 ({close:.2f} < {ema50:.2f})"
    return 5.0, f"Near EMA50 ({close:.2f} ≈ {ema50:.2f})"


def _score_bb_pct_b(pb: float) -> tuple[float, str]:
    if np.isnan(pb):
        return 5.0, "N/A"
    if pb >= 0.85:
        return 3.5, f"Near upper band (%B={pb:.2f})"
    if pb <= 0.15:
        return 7.0, f"Near lower band (%B={pb:.2f})"
    if pb >= 0.55:
        return 6.0, f"Upper half (%B={pb:.2f})"
    if pb <= 0.45:
        return 4.0, f"Lower half (%B={pb:.2f})"
    return 5.0, f"Mid band (%B={pb:.2f})"


def _score_cci(cci_v: float) -> tuple[float, str]:
    if np.isnan(cci_v):
        return 5.0, "N/A"
    if cci_v >= 100:
        return 6.5, f"Strong momentum ({cci_v:.1f})"
    if cci_v <= -100:
        return 3.5, f"Weak momentum ({cci_v:.1f})"
    return 5.0, f"Neutral momentum ({cci_v:.1f})"


def _score_stoch(k: float, d: float) -> tuple[float, str]:
    if np.isnan(k) or np.isnan(d):
        return 5.0, "N/A"
    if k >= 80 and d >= 80:
        return 3.5, f"Stoch overbought (K={k:.1f}, D={d:.1f})"
    if k <= 20 and d <= 20:
        return 7.0, f"Stoch oversold (K={k:.1f}, D={d:.1f})"
    if k > d:
        return 6.0, f"Bullish cross (K={k:.1f} > D={d:.1f})"
    return 4.0, f"Bearish cross (K={k:.1f} < D={d:.1f})"


def _score_adx(adx_v: float, plus_di: float, minus_di: float) -> tuple[float, str]:
    """Higher ADX = trend; direction from +DI vs -DI."""
    if np.isnan(adx_v):
        return 5.0, "N/A"
    if adx_v < 18:
        return 5.0, f"Weak trend (ADX={adx_v:.1f})"
    if np.isnan(plus_di) or np.isnan(minus_di):
        return 5.0, f"ADX={adx_v:.1f}"
    if plus_di > minus_di:
        return 6.8, f"Trend up (+DI {plus_di:.1f} > -DI {minus_di:.1f}), ADX {adx_v:.1f}"
    return 3.2, f"Trend down (-DI {minus_di:.1f} > +DI {plus_di:.1f}), ADX {adx_v:.1f}"


def _plus_minus_di(df: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series]:
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_ = tr.ewm(alpha=1 / period, adjust=False).mean()
    pdi = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_
    return pdi, mdi


@dataclass
class IndicatorRow:
    name: str
    bullish_score: float
    detail: str


@dataclass
class SignalBundle:
    rows: list[IndicatorRow]
    mean_score: float
    signal: str  # BUY_CE | BUY_PE | HOLD
    strength: str
    reason: str
    ce_points: int
    pe_points: int
    atr: float
    last_close: float


def _to_ce_pe_points(score: float) -> tuple[int, int]:
    """Derive discrete CE/PE points from 0–10 bullish score (for summary display)."""
    if score >= 6.2:
        return 1, 0
    if score <= 3.8:
        return 0, 1
    return 0, 0


def analyze_ohlcv(df: pd.DataFrame) -> SignalBundle:
    """Expects sorted OHLCV with lowercase columns."""
    d = df.dropna(subset=["close"]).copy()
    if len(d) < 60:
        raise ValueError("Not enough candles for indicators (need ~60+ rows).")

    close = d["close"]
    high, low = d["high"], d["low"]
    vol = d["volume"].fillna(0)

    r = ind.rsi(close, 14)
    m_line, m_sig, m_hist = ind.macd(close)
    vw = ind.vwap(d)
    ema9 = ind.ema(close, 9)
    ema21 = ind.ema(close, 21)
    ema50 = ind.ema(close, 50)
    bb = ind.bollinger_pct_b(close, 20, 2.0)
    cci_v = ind.cci(d, 20)
    k, st_d = ind.stochastic(d, 14, 3)
    adx_v = ind.adx(d, 14)
    pdi, mdi = _plus_minus_di(d, 14)
    atr_v = ind.atr(high, low, close, 14)

    vol_ma = vol.rolling(20).mean()
    vol_ratio = (vol / vol_ma.replace(0, np.nan)).iloc[-1]

    last = -1
    rsi_v = float(r.iloc[last])
    line, sig, hist = float(m_line.iloc[last]), float(m_sig.iloc[last]), float(m_hist.iloc[last])
    vw_last = float(vw.iloc[last])
    c_last = float(close.iloc[last])
    e9, e21, e50 = float(ema9.iloc[last]), float(ema21.iloc[last]), float(ema50.iloc[last])
    bb_last = float(bb.iloc[last])
    cci_last = float(cci_v.iloc[last])
    k_last, d_last = float(k.iloc[last]), float(st_d.iloc[last])
    adx_last = float(adx_v.iloc[last])
    pdi_last, mdi_last = float(pdi.iloc[last]), float(mdi.iloc[last])
    atr_last = float(atr_v.iloc[last])

    builders = [
        ("RSI (14)", _score_rsi(rsi_v)),
        ("MACD (12,26,9)", _score_macd(line, sig, hist)),
        ("VWAP position", _score_vwap(c_last, vw_last)),
        ("Volume vs 20-bar avg", _score_volume_ratio(vol_ratio)),
        ("EMA9 vs EMA21", _score_ema_cross(e9, e21)),
        ("Price vs EMA50", _score_ema50(c_last, e50)),
        ("Bollinger %B (20,2)", _score_bb_pct_b(bb_last)),
        ("CCI (20)", _score_cci(cci_last)),
        ("Stochastic (14,3,3)", _score_stoch(k_last, d_last)),
        ("ADX + DMI (14)", _score_adx(adx_last, pdi_last, mdi_last)),
    ]

    rows = [IndicatorRow(name=n, bullish_score=_clip_score(s), detail=desc) for n, (s, desc) in builders]
    mean_score = float(np.mean([r.bullish_score for r in rows]))

    ce = pe = 0
    for r in rows:
        c, p = _to_ce_pe_points(r.bullish_score)
        ce += c
        pe += p

    if mean_score >= 6.0:
        signal = "BUY_CE"
        strength = "STRONG" if mean_score >= 6.8 else "MODERATE"
        reason = f"Bullish tilt (avg score {mean_score:.2f}/10; CE +{ce} vs PE +{pe} discrete flags)."
    elif mean_score <= 4.0:
        signal = "BUY_PE"
        strength = "STRONG" if mean_score <= 3.2 else "MODERATE"
        reason = f"Bearish tilt (avg score {mean_score:.2f}/10; CE +{ce} vs PE +{pe} discrete flags)."
    else:
        signal = "HOLD"
        strength = "NEUTRAL"
        reason = f"Mixed / balanced readings (avg score {mean_score:.2f}/10). No clear directional edge."

    return SignalBundle(
        rows=rows,
        mean_score=mean_score,
        signal=signal,
        strength=strength,
        reason=reason,
        ce_points=ce,
        pe_points=pe,
        atr=atr_last,
        last_close=c_last,
    )


def atr_risk_levels(
    last_close: float,
    atr: float,
    *,
    atr_sl_mult: float = 1.2,
    rr: float = 2.0,
) -> dict[str, float]:
    if np.isnan(atr) or atr <= 0:
        return {}
    sl_dist = atr * atr_sl_mult
    tgt_dist = sl_dist * rr
    return {
        "atr": atr,
        "sl_per_unit": sl_dist,
        "target_per_unit": tgt_dist,
        "sl_price_ce_buy": last_close - sl_dist,
        "target_price_ce_buy": last_close + tgt_dist,
        "sl_price_pe_buy": last_close + sl_dist,
        "target_price_pe_buy": last_close - tgt_dist,
    }


def pick_strike_moneyness(
    spot: float,
    atm_strike: float,
    strike_step: float,
    signal: str,
    *,
    mean_score: float,
) -> dict[str, Any]:
    """
    Recommend ATM vs 1-step ITM/OTM for buyers based on conviction.
    Index strikes are typically 50 / 100 — caller passes step.
    """
    if signal == "HOLD":
        return {
            "choice": "NONE",
            "label": "No strike — stay flat or hedge existing positions.",
            "strike": None,
        }

    step = strike_step if strike_step > 0 else max(1.0, round(spot * 0.0005, 2))
    # Round ATM to step grid if needed
    atm = atm_strike
    otm_ce = atm + step
    itm_ce = atm - step
    otm_pe = atm - step
    itm_pe = atm + step

    strong = (signal == "BUY_CE" and mean_score >= 6.5) or (signal == "BUY_PE" and mean_score <= 3.5)

    if signal == "BUY_CE":
        if strong:
            choice, strike, label = "OTM", otm_ce, f"1 OTM CE @ ₹{otm_ce:,.2f} (higher risk/reward vs ATM)"
        else:
            choice, strike, label = "ATM", atm, f"ATM CE @ ₹{atm:,.2f} (balanced delta vs premium)"
        return {
            "choice": choice,
            "strike": strike,
            "label": label,
            "alternatives": {"ITM CE": itm_ce, "ATM CE": atm, "OTM CE": otm_ce},
        }

    if signal == "BUY_PE":
        if strong:
            choice, strike, label = "OTM", otm_pe, f"1 OTM PE @ ₹{otm_pe:,.2f}"
        else:
            choice, strike, label = "ATM", atm, f"ATM PE @ ₹{atm:,.2f}"
        return {
            "choice": choice,
            "strike": strike,
            "label": label,
            "alternatives": {"ITM PE": itm_pe, "ATM PE": atm, "OTM PE": otm_pe},
        }

    return {"choice": "NONE", "label": "", "strike": None}


def moneyness_label_call(spot: float, strike: float) -> str:
    if strike < spot:
        return "ITM"
    if strike > spot:
        return "OTM"
    return "ATM"


def moneyness_label_put(spot: float, strike: float) -> str:
    if strike > spot:
        return "ITM"
    if strike < spot:
        return "OTM"
    return "ATM"


def infer_strike_step(strikes: list[float], spot: float) -> float:
    if len(strikes) < 2:
        return 50.0
    s = sorted(strikes)
    diffs = [b - a for a, b in zip(s, s[1:]) if b > a]
    if not diffs:
        return 50.0
    step = min(diffs)
    return float(step) if step > 0 else 50.0


def nearest_atm_strike(strikes: list[float], spot: float) -> float:
    if not strikes:
        return round(spot / 50) * 50
    return min(strikes, key=lambda x: abs(float(x) - spot))
