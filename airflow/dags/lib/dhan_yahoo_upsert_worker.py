"""
Dhan → Yahoo map upsert logic (used in-process or from ``scripts/run_dhan_yahoo_upsert.py``).

Separated from the DAG file so Airflow can run it in a **subprocess** (fresh Python), avoiding
``engine.begin()`` / libpq stalls in forked task workers on macOS.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from sqlalchemy import MetaData, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from lib.medha_db import (
    dhan_yahoo_instrument_map_table,
    format_engine_for_log,
    get_medha_engine,
)

log = logging.getLogger("airflow.task")


def _upsert_log_every_n() -> int:
    """How often to emit INFO progress lines (default 500). ``MEDHA_UPSERT_LOG_EVERY``."""
    return max(1, int(os.environ.get("MEDHA_UPSERT_LOG_EVERY", "500") or "500"))


def _upsert_log_every_sec() -> float:
    """Minimum seconds between INFO progress lines (default 60). ``MEDHA_UPSERT_LOG_EVERY_SEC``; 0 disables."""
    return max(0.0, float(os.environ.get("MEDHA_UPSERT_LOG_EVERY_SEC", "60") or "60"))


def _upsert_log_api_timing() -> bool:
    """Log per-row API latency when true. ``MEDHA_UPSERT_LOG_API_TIMING=1``."""
    return os.environ.get("MEDHA_UPSERT_LOG_API_TIMING", "0").lower() in ("1", "true", "yes")


# When primary search ``{underlying}.NS`` / ``.BO`` returns nothing (typical for indices),
# try Yahoo Finance ``^`` symbols (second request, must still match API response).
INDEX_YAHOO_TICKERS: dict[tuple[str, str], str] = {
    ("NSE", "NIFTY"): "^NSEI",
    ("NSE", "BANKNIFTY"): "^NSEBANK",
    ("NSE", "FINNIFTY"): "^NSEFINNIFTY",
    ("NSE", "INDIA VIX"): "^INDIAVIX",
    ("BSE", "SENSEX"): "^BSESN",
    ("NSE", "NIFTYIT"): "^CNXIT",
    ("NSE", "NIFTY AUTO"): "^CNXAUTO",
    ("NSE", "NIFTY FMCG"): "^CNXFMCG",
    ("NSE", "NIFTY MEDIA"): "^CNXMEDIA",
    ("NSE", "NIFTY METAL"): "^CNXMETAL",
    ("NSE", "NIFTY REALTY"): "^CNXREALTY",
    ("NSE", "NIFTY PSU BANK"): "^CNXPSUBANK",
    ("NSE", "NIFTY PHARMA"): "^CNXPHARMA",
    ("NSE", "NIFTY ENERGY"): "^CNXENERGY",
    ("NSE", "NIFTY INFRA"): "^CNXINFRA",
    ("NSE", "NIFTY CPSE"): "^CNXCPSE",
}


def _norm_header(h: str) -> str:
    return (h or "").strip()


def _parse_bool(raw: str | None, default: bool = True) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    v = str(raw).strip().lower()
    if v in ("true", "1", "yes", "y"):
        return True
    if v in ("false", "0", "no", "n"):
        return False
    return default


def _parse_opt_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "":
        return None
    return int(s)


def _parse_opt_str(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s else None


def _ticker_compact(underlying: str) -> str:
    return "".join((underlying or "").split())


def _exch_suffix(exch_id: str) -> str | None:
    """NSE → NS, BSE → BO (EXCH_ID from Dhan)."""
    x = (exch_id or "").strip().upper()
    if x == "NSE":
        return "NS"
    if x == "BSE":
        return "BO"
    return None


def _http_get_json(url: str, *, timeout: float = 60.0) -> tuple[bool, object | str]:
    """Returns (ok, parsed_json_or_error_message)."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "MedhaAirflow/dhan-yahoo-map/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
        except OSError:
            body = ""
        return False, f"HTTP {e.code}: {body[:500]}"
    except urllib.error.URLError as e:
        return False, f"URL error: {e.reason!r}"
    except OSError as e:
        return False, f"IO error: {e!r}"
    try:
        return True, json.loads(raw)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e!r}"


def _yahoo_search_quotes(
    api_base: str,
    q: str,
    *,
    max_results: int = 1,
    timeout: float = 60.0,
) -> tuple[bool, list[dict] | str]:
    """GET ``{api_base}/search?q=...&max_results=...`` → list of quote dicts."""
    params = urllib.parse.urlencode({"q": q, "max_results": max(1, max_results)})
    url = f"{api_base}/search?{params}"
    ok, data = _http_get_json(url, timeout=timeout)
    if not ok:
        return False, str(data)
    if isinstance(data, list):
        return True, [x for x in data if isinstance(x, dict)]
    return False, f"unexpected response type {type(data).__name__}"


def _first_quote_symbol(quotes: list[dict]) -> str | None:
    if not quotes:
        return None
    sym = quotes[0].get("symbol")
    if sym is None:
        return None
    return str(sym).strip()


def _symbols_match(expected: str, actual: str | None) -> bool:
    if not actual:
        return False
    return expected.strip().upper() == actual.strip().upper()


def _resolve_yahoo_symbol_via_api(
    api_base: str,
    *,
    exch_id: str,
    instrument: str,
    underlying_symbol: str,
    csv_row: int,
) -> tuple[str | None, str]:
    """
    Returns (yahoo_symbol or None, audit note for ``notes`` / logging).
    """
    exch = (exch_id or "").strip().upper()
    inst = (instrument or "").strip().upper()
    und = (underlying_symbol or "").strip()
    suffix = _exch_suffix(exch_id)
    if not suffix:
        return None, f"unsupported EXCH_ID={exch_id!r}"
    compact = _ticker_compact(und)
    if not compact:
        return None, "empty UNDERLYING_SYMBOL"

    primary = f"{compact}.{suffix}"
    log.debug(
        "Row %d: API search primary q=%r (exch=%s inst=%s und=%r)",
        csv_row,
        primary,
        exch,
        inst,
        und,
    )
    ok, data = _yahoo_search_quotes(api_base, primary, max_results=1)
    if not ok:
        log.warning("Row %d: search failed for q=%r: %s", csv_row, primary, data)
        return None, f"search_error:{primary}:{data}"

    quotes = data if isinstance(data, list) else []
    sym = _first_quote_symbol(quotes)
    if _symbols_match(primary, sym):
        return primary, f"api_q={primary};matched=primary"

    # Indices: try mapped ^ symbol (underlying.NS often returns no quotes)
    if inst == "INDEX":
        key = (exch, und.upper())
        alt = INDEX_YAHOO_TICKERS.get(key)
        if alt:
            log.debug("Row %d: primary miss sym=%r; trying index map q=%r", csv_row, sym, alt)
            ok2, data2 = _yahoo_search_quotes(api_base, alt, max_results=1)
            if not ok2:
                log.warning("Row %d: index search failed q=%r: %s", csv_row, alt, data2)
                return None, f"search_error:{alt}:{data2}"
            quotes2 = data2 if isinstance(data2, list) else []
            sym2 = _first_quote_symbol(quotes2)
            if _symbols_match(alt, sym2):
                return alt, f"api_q={alt};matched=index_map;primary_tried={primary}"
            return None, f"no_match primary={primary} got={sym!r} alt={alt} got2={sym2!r}"

    return None, f"no_match expected={primary} got={sym!r}"


def _row_base_manual(rec: dict[str, str]) -> dict | None:
    exch = (rec.get("dhan_exch_id") or "").strip()
    und = (rec.get("dhan_underlying_symbol") or "").strip()
    if not exch or not und:
        return None
    seg = (rec.get("dhan_segment") or "").strip()
    return {
        "dhan_security_id": _parse_opt_int(rec.get("dhan_security_id")),
        "isin": _parse_opt_str(rec.get("isin")),
        "dhan_exch_id": exch,
        "dhan_segment": seg,
        "dhan_underlying_symbol": und,
        "dhan_symbol_name": _parse_opt_str(rec.get("dhan_symbol_name")),
        "dhan_display_name": _parse_opt_str(rec.get("dhan_display_name")),
        "mapping_source": _parse_opt_str(rec.get("mapping_source")) or "csv_import",
        "is_active": _parse_bool(rec.get("is_active"), default=True),
        "notes": _parse_opt_str(rec.get("notes")),
    }


def _row_base_dhan_master(rec: dict[str, str]) -> dict | None:
    instrument = (rec.get("INSTRUMENT") or "").strip().upper()
    instrument_type = (rec.get("INSTRUMENT_TYPE") or "").strip().upper()

    if instrument == "EQUITY":
        if instrument_type != "ES":
            return None
    elif instrument == "INDEX":
        pass
    else:
        return None

    exch = (rec.get("EXCH_ID") or "").strip()
    seg = (rec.get("SEGMENT") or "").strip()
    und = (rec.get("UNDERLYING_SYMBOL") or "").strip()
    if not exch or not und:
        return None

    isin_raw = (rec.get("ISIN") or "").strip()
    isin = None if isin_raw in ("", "NA", "N/A") else isin_raw

    sec_raw = (rec.get("SECURITY_ID") or "").strip()
    dhan_security_id = int(sec_raw) if sec_raw.isdigit() else None

    sym_name = _parse_opt_str(rec.get("SYMBOL_NAME"))
    disp = _parse_opt_str(rec.get("DISPLAY_NAME"))

    notes_parts = [f"dhan_instrument={instrument}", f"dhan_instrument_type={instrument_type or '-'}"]
    notes = "; ".join(notes_parts)

    return {
        "dhan_security_id": dhan_security_id,
        "isin": isin,
        "dhan_exch_id": exch,
        "dhan_segment": seg,
        "dhan_underlying_symbol": und,
        "dhan_symbol_name": sym_name,
        "dhan_display_name": disp,
        "mapping_source": "yahoo_api_search_verified",
        "is_active": True,
        "notes": notes,
        "_instrument": instrument,
        "_instrument_type": instrument_type,
    }


def run_upsert_from_cfg(cfg: dict) -> None:
    """
    Run the full upsert from a config dict (same keys as XCom from ``validate_csv_source``).

    Expected keys: ``csv_path``, ``api_base``, ``delay_sec``, ``use_dhan_master``,
    optional ``total_rows_hint``.

    **Pipeline per CSV row (streamed, not loaded entirely into RAM):**

    1. Read one row from the CSV.
    2. Call the backend Yahoo search API (``GET …/search``).
    3. If the response **matches** the expected ticker (see ``_resolve_yahoo_symbol_via_api``), get ``yahoo_symbol``.
    4. **Only if matched**, build payload and upsert into Postgres (per-row transaction).
    """
    path = Path(cfg["csv_path"])
    api_base = cfg["api_base"]
    delay = float(cfg.get("delay_sec") or 0)
    use_dhan_master = bool(cfg["use_dhan_master"])
    total_hint = int(cfg.get("total_rows_hint") or cfg.get("total_rows") or 0)

    log.info(
        "Task=upsert_dhan_yahoo_map phase=start csv=%s use_dhan_master=%s total_rows_hint=%d api_base=%r",
        path,
        use_dhan_master,
        total_hint,
        api_base,
    )

    log.info(
        "Task=upsert_dhan_yahoo_map pipeline steps: (1) read_csv_row (2) backend GET /search (3) match? (4) db upsert if matched; "
        "stream CSV (no full-file list in memory); total_rows_hint=%d",
        total_hint,
    )

    log.info(
        "Task=upsert_dhan_yahoo_map db: dhan_yahoo_instrument_map_table() from lib.medha_db (no reflect)"
    )
    engine = get_medha_engine()
    log.info(
        "Task=upsert_dhan_yahoo_map db_engine url=%s (same backend DB; sync driver)",
        format_engine_for_log(engine),
    )
    metadata = MetaData()
    table = dhan_yahoo_instrument_map_table(metadata)
    log.info(
        "Task=upsert_dhan_yahoo_map db_table ok name=%r columns=%s",
        table.name,
        sorted(table.c.keys()),
    )

    rows_loaded = 0
    rows_skipped_empty = 0
    rows_filtered = 0
    rows_api_no_match = 0
    rows_error = 0
    rows_skipped_security_id = 0
    total_to_process = total_hint if total_hint > 0 else 0
    log_every = _upsert_log_every_n()
    log_every_sec = _upsert_log_every_sec()
    log_api_timing = _upsert_log_api_timing()
    log.info(
        "Task=upsert_dhan_yahoo_map row_loop streaming (hint total_rows=%d); each row: csv→api→match→db if matched",
        total_to_process or total_hint,
    )
    if total_to_process == 0:
        log.warning(
            "Task=upsert_dhan_yahoo_map total_rows_hint is 0 — ETA uses row index only; "
            "ensure validate_csv_source XCom includes total_rows",
        )
    log.info(
        "Task=upsert_dhan_yahoo_map log_config MEDHA_UPSERT_LOG_EVERY=%d MEDHA_UPSERT_LOG_EVERY_SEC=%.1f "
        "MEDHA_UPSERT_LOG_API_TIMING=%s delay_sec=%.4f",
        log_every,
        log_every_sec,
        log_api_timing,
        delay,
    )

    txn_t0 = time.monotonic()
    log.info(
        "Task=upsert_dhan_yahoo_map db_txn one transaction per upsert row (commit after each successful write; "
        "partial progress survives failures)"
    )

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row.")

        with engine.connect() as conn:
            after_begin = time.monotonic()
            log.info(
                "Task=upsert_dhan_yahoo_map db connect in %.3fs pool=%s dialect=%s driver=%s",
                after_begin - txn_t0,
                type(engine.pool).__name__,
                engine.dialect.name,
                engine.url.drivername,
            )
            t_loop = time.monotonic()
            last_log_t = t_loop
            for idx, raw in enumerate(reader, start=1):
                try:
                    rec = {
                        _norm_header(k): (str(v).strip() if v is not None else "")
                        for k, v in raw.items()
                    }
                    if not any(rec.values()):
                        rows_skipped_empty += 1
                        log.debug("Row %d/%d: skip empty", idx, total_to_process)
                        continue

                    if idx <= 3:
                        log.info(
                            "Task=upsert_dhan_yahoo_map row=%d step=1_read_csv (streaming one row)",
                            idx,
                        )

                    try:
                        t_api = time.monotonic()
                        if use_dhan_master:
                            base = _row_base_dhan_master(rec)
                            if base is None:
                                rows_filtered += 1
                                log.debug(
                                    "Row %d/%d: filtered (not EQUITY+ES or INDEX)",
                                    idx,
                                    total_to_process,
                                )
                                continue
                            instrument = str(base.pop("_instrument", "EQUITY"))
                            base.pop("_instrument_type", None)
                            yahoo, yahoo_audit = _resolve_yahoo_symbol_via_api(
                                api_base,
                                exch_id=base["dhan_exch_id"],
                                instrument=instrument,
                                underlying_symbol=base["dhan_underlying_symbol"],
                                csv_row=idx,
                            )
                        else:
                            base = _row_base_manual(rec)
                            if base is None:
                                rows_filtered += 1
                                continue
                            yahoo, yahoo_audit = _resolve_yahoo_symbol_via_api(
                                api_base,
                                exch_id=base["dhan_exch_id"],
                                instrument="EQUITY",
                                underlying_symbol=base["dhan_underlying_symbol"],
                                csv_row=idx,
                            )
                        api_ms = (time.monotonic() - t_api) * 1000.0
                        if idx <= 3:
                            log.info(
                                "Task=upsert_dhan_yahoo_map row=%d step=2_api_backend done api_ms=%.1f",
                                idx,
                                api_ms,
                            )
                        if idx <= 5 or log_api_timing:
                            log.info(
                                "Task=upsert_dhan_yahoo_map row=%d/%d timing api_ms=%.1f underlying=%r exch=%r",
                                idx,
                                total_to_process,
                                api_ms,
                                base.get("dhan_underlying_symbol"),
                                base.get("dhan_exch_id"),
                            )
                    except Exception as e:
                        rows_error += 1
                        log.exception(
                            "Task=upsert_dhan_yahoo_map row=%d/%d: unexpected error during Yahoo resolve: %s",
                            idx,
                            total_to_process,
                            e,
                        )
                        continue

                    if yahoo is None:
                        rows_api_no_match += 1
                        if idx <= 3:
                            log.info(
                                "Task=upsert_dhan_yahoo_map row=%d step=3_match NO → skip DB (underlying=%r)",
                                idx,
                                base.get("dhan_underlying_symbol"),
                            )
                        log.info(
                            "Row %d/%d: NO_UPSERT underlying=%r exch=%r reason=%s",
                            idx,
                            total_to_process,
                            base.get("dhan_underlying_symbol"),
                            base.get("dhan_exch_id"),
                            yahoo_audit,
                        )
                        continue

                    if idx <= 3:
                        log.info(
                            "Task=upsert_dhan_yahoo_map row=%d step=3_match YES yahoo=%r → step=4_db_upsert",
                            idx,
                            yahoo,
                        )

                    payload = {
                        **base,
                        "yahoo_symbol": yahoo,
                        "mapping_source": "yahoo_api_search_verified",
                        "notes": "; ".join(
                            x
                            for x in (
                                base.get("notes"),
                                yahoo_audit,
                            )
                            if x
                        ),
                    }
                    for k in list(payload.keys()):
                        if k not in table.c:
                            payload.pop(k, None)

                    if idx <= 5 or idx % 100 == 0:
                        log.info(
                            "Row %d/%d: UPSERT key=(exch=%r seg=%r und=%r) yahoo=%r sec_id=%r",
                            idx,
                            total_to_process,
                            payload.get("dhan_exch_id"),
                            payload.get("dhan_segment"),
                            payload.get("dhan_underlying_symbol"),
                            payload.get("yahoo_symbol"),
                            payload.get("dhan_security_id"),
                        )
                    else:
                        log.debug(
                            "Row %d/%d: upsert und=%r yahoo=%r",
                            idx,
                            total_to_process,
                            payload.get("dhan_underlying_symbol"),
                            payload.get("yahoo_symbol"),
                        )

                    t_exec = time.monotonic()
                    stmt = insert(table).values(**payload)
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_dhan_yahoo_dhan_symbol_exch_seg",
                        set_={
                            "dhan_security_id": stmt.excluded.dhan_security_id,
                            "isin": stmt.excluded.isin,
                            "dhan_symbol_name": stmt.excluded.dhan_symbol_name,
                            "dhan_display_name": stmt.excluded.dhan_display_name,
                            "yahoo_symbol": stmt.excluded.yahoo_symbol,
                            "mapping_source": stmt.excluded.mapping_source,
                            "is_active": stmt.excluded.is_active,
                            "notes": stmt.excluded.notes,
                            "updated_at": func.now(),
                        },
                    )
                    sid = payload.get("dhan_security_id")
                    skip_row = False
                    skip_reason = ""
                    with conn.begin():
                        if sid is not None:
                            ex_row = conn.execute(
                                select(
                                    table.c.dhan_exch_id,
                                    table.c.dhan_segment,
                                    table.c.dhan_underlying_symbol,
                                ).where(table.c.dhan_security_id == sid)
                            ).first()
                            if ex_row is not None:
                                ex, sg, und = ex_row[0], ex_row[1], ex_row[2]
                                if (
                                    ex != payload.get("dhan_exch_id")
                                    or sg != payload.get("dhan_segment")
                                    or und != payload.get("dhan_underlying_symbol")
                                ):
                                    skip_row = True
                                    skip_reason = (
                                        f"dhan_security_id={sid} already mapped to "
                                        f"exch={ex!r} seg={sg!r} und={und!r}"
                                    )
                        if not skip_row:
                            try:
                                conn.execute(stmt)
                            except IntegrityError as ie:
                                o = str(ie.orig)
                                if "uq_dhan_yahoo_dhan_security_id" in o or "dhan_security_id" in o:
                                    skip_row = True
                                    skip_reason = o.strip()
                                else:
                                    raise
                    if skip_row:
                        rows_skipped_security_id += 1
                        log.warning(
                            "Task=upsert_dhan_yahoo_map row=%d/%d: SKIP %s",
                            idx,
                            total_to_process,
                            skip_reason or "security_id conflict",
                        )
                    else:
                        exec_ms = (time.monotonic() - t_exec) * 1000.0
                        if idx <= 5 or log_api_timing:
                            log.info(
                                "Task=upsert_dhan_yahoo_map row=%d/%d timing db_execute_ms=%.1f",
                                idx,
                                total_to_process,
                                exec_ms,
                            )
                        rows_loaded += 1

                    if delay > 0:
                        time.sleep(delay)
                finally:
                    now = time.monotonic()
                    if idx == 1 or idx % log_every == 0 or (
                        log_every_sec > 0 and (now - last_log_t) >= log_every_sec
                    ):
                        elapsed = now - t_loop
                        rate = idx / elapsed if elapsed > 0 else 0.0
                        eta = (
                            (total_to_process - idx) * (elapsed / idx)
                            if idx > 0 and total_to_process > 0
                            else 0.0
                        )
                        log.info(
                            "Task=upsert_dhan_yahoo_map progress row=%d/%d elapsed=%.1fs rate=%.2f rows/s "
                            "upserted=%d no_match=%d filtered=%d empty=%d err=%d skip_sec_id=%d eta≈%.0fs",
                            idx,
                            total_to_process,
                            elapsed,
                            rate,
                            rows_loaded,
                            rows_api_no_match,
                            rows_filtered,
                            rows_skipped_empty,
                            rows_error,
                            rows_skipped_security_id,
                            eta,
                        )
                        last_log_t = now

    txn_wall = time.monotonic() - txn_t0
    log.info(
        "Task=upsert_dhan_yahoo_map db wall=%.1fs (per-row commits; no single global rollback)",
        txn_wall,
    )
    log.info(
        "Task=upsert_dhan_yahoo_map phase=done upserted=%d api_no_match=%d filtered=%d empty=%d errors=%d "
        "skip_security_id=%d wall=%.1fs csv=%s api_base=%s",
        rows_loaded,
        rows_api_no_match,
        rows_filtered,
        rows_skipped_empty,
        rows_error,
        rows_skipped_security_id,
        txn_wall,
        path,
        api_base,
    )
