"""Paths and defaults."""

from pathlib import Path

# options-dashboard/ root (parent of app/)
_DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
# Repo root (parent of options-dashboard/), for legacy instrument CSV layout
_REPO_ROOT = Path(__file__).resolve().parents[2]

_INSTRUMENT_CANDIDATES = (
    _DASHBOARD_ROOT / "data" / "dhan-instrument-list_full.csv",
    _REPO_ROOT / "dhan-Instrument List" / "dhan-instrument-list_full.csv",
)

DEFAULT_INSTRUMENT_CSV = next((p for p in _INSTRUMENT_CANDIDATES if p.is_file()), _INSTRUMENT_CANDIDATES[0])

# NSE index: security_id, display name, typical lot (may change — verify with broker)
INDEX_INSTRUMENTS = {
    "NIFTY 50": {"security_id": 13, "lot_size": 75},
    "BANK NIFTY": {"security_id": 25, "lot_size": 15},
    "FIN NIFTY": {"security_id": 27, "lot_size": 25},
}

# MCX: resolve front-month FUTCOM from CSV by symbol name on underlying
MCX_UNDERLYINGS = {
    "SILVER FUT": "SILVER",
    "CRUDE OIL FUT": "CRUDEOIL",
}

INTERVAL_MINUTES = (1, 5, 15, 25, 60)

OPTION_CHAIN_MIN_INTERVAL_SEC = 3.1
