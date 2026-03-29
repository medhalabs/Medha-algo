"""Resolve MCX front-month futures from Dhan instrument CSV."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from app.config import DEFAULT_INSTRUMENT_CSV


@dataclass(frozen=True)
class McxFuture:
    security_id: int
    trading_symbol: str
    expiry: datetime
    lot_units: float
    tick_size: float
    symbol_name: str


def _parse_expiry(raw: str) -> datetime | None:
    if pd.isna(raw) or not str(raw).strip():
        return None
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt) if len(s) >= 19 else datetime.strptime(s[:10], fmt)
        except ValueError:
            continue
    return None


def resolve_mcx_front_future(
    underlying_name: str,
    csv_path: str | None = None,
    *,
    as_of: datetime | None = None,
) -> McxFuture | None:
    """
    Pick nearest active SILVER / CRUDEOIL **monthly** future (FUTCOM), excluding
    mini contracts (SILVERM, CRUDEOILM) by matching trading symbol prefix.
    """
    path = csv_path or str(DEFAULT_INSTRUMENT_CSV)
    df = pd.read_csv(
        path,
        low_memory=False,
        usecols=[
            "SEM_EXM_EXCH_ID",
            "SEM_SEGMENT",
            "SEM_SMST_SECURITY_ID",
            "SEM_INSTRUMENT_NAME",
            "SEM_TRADING_SYMBOL",
            "SEM_LOT_UNITS",
            "SEM_EXPIRY_DATE",
            "SEM_TICK_SIZE",
            "SM_SYMBOL_NAME",
        ],
    )
    df = df[
        (df["SEM_EXM_EXCH_ID"] == "MCX")
        & (df["SEM_SEGMENT"] == "M")
        & (df["SEM_INSTRUMENT_NAME"] == "FUTCOM")
    ]
    # Main contract: SILVER-... or CRUDEOIL-... but not SILVERM / CRUDEOILM
    pat = re.compile(rf"^{re.escape(underlying_name)}-\d+[A-Za-z]+\d{{4}}-FUT$")
    df = df[df["SEM_TRADING_SYMBOL"].astype(str).str.match(pat, na=False)]
    if df.empty:
        return None

    df = df.copy()
    df["_exp"] = df["SEM_EXPIRY_DATE"].apply(_parse_expiry)
    df = df.dropna(subset=["_exp"])
    now = as_of or datetime.now()
    df = df[df["_exp"] >= now.replace(hour=0, minute=0, second=0, microsecond=0)]
    if df.empty:
        df = pd.read_csv(
            path,
            usecols=[
                "SEM_EXM_EXCH_ID",
                "SEM_SEGMENT",
                "SEM_SMST_SECURITY_ID",
                "SEM_INSTRUMENT_NAME",
                "SEM_TRADING_SYMBOL",
                "SEM_LOT_UNITS",
                "SEM_EXPIRY_DATE",
                "SEM_TICK_SIZE",
                "SM_SYMBOL_NAME",
            ],
        )
        df = df[
            (df["SEM_EXM_EXCH_ID"] == "MCX")
            & (df["SEM_SEGMENT"] == "M")
            & (df["SEM_INSTRUMENT_NAME"] == "FUTCOM")
        ]
        df = df[df["SEM_TRADING_SYMBOL"].astype(str).str.match(pat, na=False)]
        df["_exp"] = df["SEM_EXPIRY_DATE"].apply(_parse_expiry)
        df = df.dropna(subset=["_exp"])

    row = df.sort_values("_exp").iloc[0]
    return McxFuture(
        security_id=int(row["SEM_SMST_SECURITY_ID"]),
        trading_symbol=str(row["SEM_TRADING_SYMBOL"]),
        expiry=row["_exp"],
        lot_units=float(row["SEM_LOT_UNITS"]),
        tick_size=float(row["SEM_TICK_SIZE"]),
        symbol_name=str(row["SM_SYMBOL_NAME"]),
    )
