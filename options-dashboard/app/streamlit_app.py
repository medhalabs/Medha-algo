"""Streamlit UI: Dhan-only option signal dashboard."""

from __future__ import annotations

import os
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from dhanhq import dhanhq

from app.config import INDEX_INSTRUMENTS
from app import dhan_fetch as dh
from app.instruments import resolve_mcx_front_future
from app.ui_theme import inject_theme
from app import chain_insights as ci
from app.signals import (
    analyze_ohlcv,
    atr_risk_levels,
    infer_strike_step,
    moneyness_label_call,
    moneyness_label_put,
    nearest_atm_strike,
    pick_strike_moneyness,
)


def _style_signal(sig: str) -> str:
    """Markdown line for summary / captions (not for `st.metric` — use `_signal_metric_plain`)."""
    if sig == "BUY_CE":
        return "🟢 **BUY CE (Call)**"
    if sig == "BUY_PE":
        return "🔴 **BUY PE (Put)**"
    return "🟡 **HOLD / no new directional**"


def _signal_metric_plain(sig: str) -> str:
    """Short plain labels so metric cards are not clipped (Streamlit metrics ellipsis long values)."""
    if sig == "BUY_CE":
        return "BUY CE"
    if sig == "BUY_PE":
        return "BUY PE"
    return "HOLD"


@st.cache_data(ttl=120, show_spinner=False)
def _load_ohlc_cached(
    client_id: str,
    access_token: str,
    security_id: int,
    exchange_segment: str,
    instrument_type: str,
    interval: int,
    _bucket: int,
    _nonce: int,
) -> pd.DataFrame:
    c = dhanhq(client_id, access_token)
    return dh.fetch_intraday(c, security_id, exchange_segment, instrument_type, interval)


@st.cache_data(ttl=600, show_spinner=False)
def _load_expiry_cached(
    client_id: str,
    access_token: str,
    under_id: int,
    under_seg: str,
) -> list[str]:
    c = dhanhq(client_id, access_token)
    return dh.fetch_expiry_list(c, under_id, under_seg)


@st.cache_data(ttl=120, show_spinner=False)
def _load_chain_cached(
    client_id: str,
    access_token: str,
    under_id: int,
    under_seg: str,
    expiry: str,
    _bucket: int,
    _nonce: int,
) -> dict[str, Any]:
    c = dhanhq(client_id, access_token)
    return dh.fetch_option_chain(c, under_id, under_seg, expiry)


def _credentials() -> tuple[str, str]:
    cid = os.getenv("DHAN_CLIENT_ID", "").strip()
    tok = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    return cid, tok


def _instrument_meta(instrument: str) -> dict[str, Any] | None:
    if instrument in INDEX_INSTRUMENTS:
        meta = INDEX_INSTRUMENTS[instrument]
        return {
            "sec_id": meta["security_id"],
            "lot": meta["lot_size"],
            "ex_seg": dhanhq.INDEX,
            "inst_type": "INDEX",
            "chain_seg": dhanhq.INDEX,
            "label": instrument,
        }
    und = "SILVER" if "SILVER" in instrument else "CRUDEOIL"
    fut = resolve_mcx_front_future(und)
    if fut is None:
        return None
    return {
        "sec_id": fut.security_id,
        "lot": fut.lot_units,
        "ex_seg": dhanhq.MCX,
        "inst_type": "FUTCOM",
        "chain_seg": dhanhq.MCX,
        "label": f"{fut.symbol_name} — {fut.trading_symbol}",
    }


def _strike_table(
    spot: float,
    strikes: list[float],
    *,
    highlight_strike: float | None,
    center: int = 7,
) -> pd.DataFrame:
    if not strikes:
        return pd.DataFrame()
    atm = nearest_atm_strike(strikes, spot)
    idx = strikes.index(atm) if atm in strikes else min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
    lo = max(0, idx - center // 2)
    hi = min(len(strikes), lo + center)
    rows = []
    for k in strikes[lo:hi]:
        ce_l = moneyness_label_call(spot, float(k))
        pe_l = moneyness_label_put(spot, float(k))
        hs = highlight_strike is not None and abs(float(k) - float(highlight_strike)) < 1e-3
        rows.append(
            {
                "Strike price": float(k),
                "Call option": ce_l,
                "Put option": pe_l,
                "Strike minus spot (points)": round(float(k) - spot, 2),
                "Highlighted by signal?": "Yes" if hs else "",
            }
        )
    return pd.DataFrame(rows)


def _style_moneyness_df(df: pd.DataFrame) -> Any:
    """Color ITM / ATM / OTM; outline row when signal suggests that strike."""

    def _leg_color(val: Any) -> str:
        if val not in ("ITM", "ATM", "OTM"):
            return ""
        if val == "ITM":
            return "background-color: rgba(0, 220, 160, 0.3); color: #042018; font-weight: 600;"
        if val == "ATM":
            return "background-color: rgba(255, 210, 100, 0.28); color: #2a2208; font-weight: 600;"
        return "background-color: rgba(100, 150, 210, 0.18); color: #0e1520;"

    def _row_frame(row: pd.Series) -> list[str]:
        pick = str(row.get("Highlighted by signal?", "")).strip().lower() == "yes"
        base = "box-shadow: inset 0 0 0 2px rgba(0, 229, 255, 0.65); background-color: rgba(0, 229, 255, 0.06);"
        return [base if pick else ""] * len(row)

    sty = df.style.map(_leg_color, subset=["Call option", "Put option"])
    return sty.apply(_row_frame, axis=1)


def _style_indicator_df(df: pd.DataFrame) -> Any:
    """Color bullish score cells: green / amber / red by threshold."""

    def _score_color(v: Any) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        try:
            x = float(v)
        except (TypeError, ValueError):
            return ""
        if x >= 6.2:
            return "background-color: rgba(0, 255, 200, 0.28); color: #031a14; font-weight: 600;"
        if x <= 3.8:
            return "background-color: rgba(255, 95, 130, 0.28); color: #2a0a12; font-weight: 600;"
        return "background-color: rgba(255, 210, 90, 0.2); color: #2a2210;"

    return df.style.map(_score_color, subset=["Bullish score (/10)"])


def _style_chain_wide_df(df: pd.DataFrame, atm: float) -> Any:
    """Highlight ATM strike row."""

    def _row_colors(row: pd.Series) -> list[str]:
        try:
            is_atm = abs(float(row["Strike"]) - float(atm)) < 1e-2
        except (TypeError, ValueError):
            is_atm = False
        base = "background-color: rgba(0, 229, 255, 0.12); font-weight: 600;" if is_atm else ""
        return [base] * len(row)

    return df.style.apply(_row_colors, axis=1)


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    st.set_page_config(
        page_title="Medha · Options Lab",
        page_icon="◈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()
    st.markdown(
        """
        <div class="medha-hero">
          <div class="medha-hero__badge">MEDHA · OPTIONS LAB</div>
          <h1 class="medha-hero__title">Signal console</h1>
          <p class="medha-hero__sub">Dhan-backed readout · Educational only — not financial advice.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Verify prices and Greeks on a live terminal before acting.")

    if "_nonce" not in st.session_state:
        st.session_state._nonce = 0

    with st.sidebar:
        st.markdown("### Control deck")
        st.caption("`DHAN_CLIENT_ID` + `DHAN_ACCESS_TOKEN` from env or `.env` in this folder.")
        cid, tok = _credentials()
        if not cid or not tok:
            cid = st.text_input("Client ID", type="default")
            tok = st.text_input("Access token", type="password")
        instrument = st.selectbox(
            "Underlying",
            [
                "NIFTY 50",
                "BANK NIFTY",
                "FIN NIFTY",
                "SILVER FUT (MCX)",
                "CRUDE OIL FUT (MCX)",
            ],
        )
        interval = st.selectbox("Candle interval (minutes)", [5, 15, 1, 25, 60], index=0)
        auto_refresh = st.checkbox(
            "Auto-refresh on interval",
            value=True,
            help=f"Reload OHLC + option chain every {interval} min (minimum 15s).",
        )
        rr = st.slider("Risk : reward (target vs SL distance)", 1.0, 3.0, 2.0, 0.5)
        atr_mult = st.slider("ATR multiplier for SL", 0.8, 2.0, 1.2, 0.1)
        st.caption("Manual refresh bumps cache immediately; auto uses your candle interval.")

    if not cid or not tok:
        st.error("Provide Dhan credentials via sidebar or environment variables.")
        return

    meta = _instrument_meta(instrument)
    if meta is None:
        st.error("Could not resolve MCX future from instrument CSV.")
        return

    try:
        expiries = _load_expiry_cached(cid, tok, meta["sec_id"], meta["chain_seg"])
    except Exception as e:
        st.error(f"Expiry list: {e}")
        st.caption("If you see auth errors, regenerate the access token in Dhan.")
        return

    if not expiries:
        st.error("No expiries returned for this underlying.")
        return

    default_exp = dh.pick_next_expiry(expiries)
    def_idx = expiries.index(default_exp) if default_exp in expiries else 0

    with st.sidebar:
        st.divider()
        expiry = st.selectbox(
            "Option expiry",
            options=expiries,
            index=min(def_idx, len(expiries) - 1),
            key=f"expiry_pick_{instrument}",
            help="Chain + PCR use this expiry.",
        )
        chain_rows = st.slider("Strikes in chain view", 9, 31, 17, 2)
        refresh_now = st.button("Refresh data now", type="primary")

    if refresh_now:
        st.session_state._nonce = st.session_state._nonce + 1

    sec_id = meta["sec_id"]
    lot = meta["lot"]
    ex_seg = meta["ex_seg"]
    inst_type = meta["inst_type"]
    chain_seg = meta["chain_seg"]
    label = meta["label"]

    nonce = int(st.session_state._nonce)
    bucket = dh.refresh_bucket(interval)

    def render_panel() -> None:
        st.session_state["_last_tick"] = time.strftime("%H:%M:%S")
        with st.spinner("Loading OHLC…"):
            ohlc = _load_ohlc_cached(cid, tok, sec_id, ex_seg, inst_type, interval, bucket, nonce)
        bundle = analyze_ohlcv(ohlc)
        risk = atr_risk_levels(bundle.last_close, bundle.atr, atr_sl_mult=atr_mult, rr=rr)

        with st.spinner("Loading option chain (rate-limited)…"):
            chain = _load_chain_cached(cid, tok, sec_id, chain_seg, expiry, bucket, nonce)

        spot, strikes, raw_oc = dh.strikes_from_chain(chain)
        if spot <= 0:
            spot = bundle.last_close
        step = infer_strike_step(strikes, spot)
        atm = nearest_atm_strike(strikes, spot) if strikes else round(spot / step) * step
        rec = pick_strike_moneyness(spot, atm, step, bundle.signal, mean_score=bundle.mean_score)
        oi_sum = dh.chain_oi_summary(raw_oc, strikes)

        st.markdown(f'<p class="medha-underline">{label}</p>', unsafe_allow_html=True)
        tick = st.session_state.get("_last_tick", "")
        mode = "Auto" if auto_refresh else "Manual"
        st.caption(f"{mode} refresh · last load **{tick}** · candle **{interval}m** · expiry **{expiry[:10]}**")

        m1, m2, m3 = st.columns(3)
        m1.metric("Signal", _signal_metric_plain(bundle.signal))
        m2.metric("Strength", bundle.strength)
        m3.metric("Avg score", f"{bundle.mean_score:.2f} / 10")
        st.caption(_style_signal(bundle.signal))

        n1, n2, n3, n4 = st.columns(4)
        n1.metric("Spot / last", f"{spot:,.2f}")
        pcr = oi_sum.get("pcr_oi")
        n2.metric("PCR (OI)", "—" if pcr != pcr or pcr is None else f"{float(pcr):.3f}")
        n3.metric("OI — call side", f"{oi_sum.get('total_ce_oi', 0):,.0f}")
        n4.metric("OI — put side", f"{oi_sum.get('total_pe_oi', 0):,.0f}")

        st.markdown(f"**Summary:** {bundle.reason}")
        st.caption(f"Discrete flags: CE-aligned {bundle.ce_points}/10 · PE-aligned {bundle.pe_points}/10")

        st.markdown(
            '<h3 class="medha-section-title">Expiry · ATM · flow (same chain snapshot)</h3>',
            unsafe_allow_html=True,
        )
        ec1, ec2 = st.columns([1, 1])
        with ec1:
            st.write(f"**Time to expiry:** {ci.expiry_label(expiry)}")
            iv_ce, iv_pe = ci.atm_iv_pair(raw_oc, atm)
            st.write(f"**ATM implied vol:** CE **{iv_ce}** · PE **{iv_pe}**")
            ap = ci.atm_combined_premium(raw_oc, atm)
            if ap:
                st.write(f"**ATM straddle premium (CE LTP + PE LTP):** {ap}")
            st.write(
                f"**Session volume (all strikes):** CE **{oi_sum.get('total_ce_vol', 0):,.0f}** · "
                f"PE **{oi_sum.get('total_pe_vol', 0):,.0f}**"
            )
            bce, bpe = ci.max_oi_strike_each_side(raw_oc, strikes)
            if bce:
                st.write(f"**Largest CE open interest:** strike **{bce[0]:,.2f}** · OI **{bce[1]:,.0f}**")
            if bpe:
                st.write(f"**Largest PE open interest:** strike **{bpe[0]:,.2f}** · OI **{bpe[1]:,.0f}**")
            st.caption("IV and LTP are live snapshots from the chain — confirm bid/ask before trading.")
        with ec2:
            st.markdown("**Underlying close** (most recent candles)")
            tail_n = min(200, len(ohlc))
            tail = ohlc.tail(tail_n)
            chart_df = tail.set_index("ts")[["close"]].rename(columns={"close": "Close"})
            st.line_chart(chart_df, use_container_width=True, height=240)
            st.caption(f"{tail_n} bars · {interval}m timeframe")

        snap = ci.suggested_leg_snapshot(bundle.signal, rec, raw_oc)
        st.markdown(
            '<h3 class="medha-section-title">Suggested contract (from signal strike)</h3>',
            unsafe_allow_html=True,
        )
        if snap:
            qrow = {
                "Strike": snap["strike"],
                "Leg": snap["side_name"],
                "LTP": snap["ltp"],
                "IV": snap["iv"],
                "Δ": snap["delta"],
                "Γ": snap["gamma"],
                "Θ": snap["theta"],
                "Vega": snap["vega"],
                "OI": snap["oi"],
                "Volume": snap["volume"],
                "OI vs prev": snap["oi_ch"],
                "Bid–ask vs mid": snap["spread"],
            }
            st.dataframe(pd.DataFrame([qrow]), use_container_width=True, hide_index=True)
            st.caption(
                "Greeks and spread are from the chain payload for this strike; illiquid strikes may show wide spreads."
            )
        else:
            st.info(
                "No single option leg is highlighted while the signal is **HOLD**, or strike data is missing. "
                "Use **ATM** context above and the full chain table below."
            )

        ic1, ic2 = st.columns([1, 1])
        with ic1:
            st.markdown(
                '<h3 class="medha-section-title">Indicator scores · 0 bearish → 10 bullish</h3>',
                unsafe_allow_html=True,
            )
            tbl = pd.DataFrame(
                [
                    {
                        "Indicator": r.name,
                        "Bullish score (/10)": round(r.bullish_score, 2),
                        "Detail": r.detail,
                    }
                    for r in bundle.rows
                ]
            )
            st.dataframe(
                _style_indicator_df(tbl),
                use_container_width=True,
                hide_index=True,
                height=min(520, 42 * (len(tbl) + 2)),
            )

        with ic2:
            st.markdown(
                '<h3 class="medha-section-title">Risk · ATR-based (illustrative)</h3>',
                unsafe_allow_html=True,
            )
            if risk:
                st.write(
                    f"ATR(14) ≈ **{risk['atr']:.4f}** · SL distance **{risk['sl_per_unit']:.4f}** · "
                    f"Target distance **{risk['target_per_unit']:.4f}** (R:R 1:{rr:.1f})"
                )
                if bundle.signal == "BUY_CE":
                    st.write(
                        f"Reference levels vs **underlying**: SL **{risk['sl_price_ce_buy']:.2f}** · "
                        f"Target **{risk['target_price_ce_buy']:.2f}**"
                    )
                elif bundle.signal == "BUY_PE":
                    st.write(
                        f"Reference levels vs **underlying**: SL **{risk['sl_price_pe_buy']:.2f}** · "
                        f"Target **{risk['target_price_pe_buy']:.2f}**"
                    )
                else:
                    st.write("No directional reference levels while signal is HOLD.")
                st.caption(
                    f"Per-lot risk/profit (underlying points × lot factor {lot}): "
                    f"≈ ₹{risk['sl_per_unit'] * lot:,.2f} / ₹{risk['target_per_unit'] * lot:,.2f} — "
                    "confirm lot size on your contract master."
                )
            else:
                st.warning("ATR not available.")

            st.markdown('<h3 class="medha-section-title">Strike suggestion</h3>', unsafe_allow_html=True)
            st.write(rec.get("label", "—"))
            if rec.get("alternatives"):
                st.json(rec["alternatives"])

        st.markdown(
            '<h3 class="medha-section-title">Option chain · LTP · OI · volume · IV · Greeks · bid/ask</h3>',
            unsafe_allow_html=True,
        )
        chain_df = dh.option_chain_detail_df(
            raw_oc,
            strikes,
            spot,
            center=chain_rows,
            atm_strike=atm,
        )
        if chain_df.empty:
            st.info("No option chain rows for this expiry.")
        else:
            st.dataframe(
                _style_chain_wide_df(chain_df, atm),
                use_container_width=True,
                hide_index=True,
                height=min(640, 36 * (len(chain_df) + 2)),
            )

        st.markdown(
            '<h3 class="medha-section-title">Strike vs spot — what ITM / OTM means here</h3>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"**Spot (underlying last) ≈ {spot:,.2f}** · Compare each strike to that level. "
            "**Call:** ITM if strike is *below* spot (call gains if spot rises). "
            "**Put:** ITM if strike is *above* spot (put gains if spot falls). "
            "**Strike minus spot** = how far the strike is from the last price (negative = strike below spot). "
            "**Highlighted by signal** = the strike the scorer picked for CE/PE (if any)."
        )
        hs = rec.get("strike")
        try:
            hs_f = float(hs) if hs is not None else None
        except (TypeError, ValueError):
            hs_f = None
        mny_df = _strike_table(spot, strikes, highlight_strike=hs_f)
        if mny_df.empty:
            st.info("No strikes in range.")
        else:
            st.dataframe(
                _style_moneyness_df(mny_df),
                use_container_width=True,
                hide_index=True,
                height=min(420, 40 * (len(mny_df) + 2)),
            )

        st.markdown('<h3 class="medha-section-title">Chain meta</h3>', unsafe_allow_html=True)
        st.caption(
            f"Expiry **{expiry}** · step **{step}** · ATM ≈ **{atm}** · strikes in chain **{oi_sum.get('strikes_count', 0)}**"
        )

    refresh_td = timedelta(seconds=max(15, int(interval) * 60))
    try:
        if auto_refresh:
            st.fragment(run_every=refresh_td)(render_panel)()
        else:
            render_panel()
    except Exception as e:
        st.error(str(e))
        st.caption("If you see auth errors, regenerate the access token in Dhan. Data API subscription is required.")


if __name__ == "__main__":
    main()
