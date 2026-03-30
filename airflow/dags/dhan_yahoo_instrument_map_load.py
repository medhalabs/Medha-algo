"""
Load ``dhan_yahoo_instrument_map`` from CSV with **Yahoo search API verification**.

**Default CSV:** ``dhan-Instrument List/stocks_and_index.csv`` (Dhan master export).
Keeps **listed equities** (``INSTRUMENT=EQUITY``, ``INSTRUMENT_TYPE=ES``) and **indices**
(``INSTRUMENT=INDEX``). For each row, calls the Medha backend
``GET /api/yahoo-apis/search?q=<UNDERLYING>.NS|BO&max_results=1`` (``NSE`` → ``.NS``,
``BSE`` → ``.BO``). The DB is updated only when the response lists a quote whose
``symbol`` matches the expected ticker. Unmapped indices may use a second search
against the known ``^`` Yahoo symbol.

**Legacy CSV** (no ``EXCH_ID``): same API check using ``dhan_exch_id`` + ``dhan_underlying_symbol``.

**Config:** ``MEDHA_YAHOO_API_BASE_URL`` (default ``http://localhost:8000/api/yahoo-apis``),
``medha_yahoo_api_base_url`` Airflow Variable, ``MEDHA_DHAN_YAHOO_CSV_PATH`` / Variable for CSV.

**Database:** Same target as FastAPI — ``DATABASE_URL`` in ``backend/.env`` (``postgresql+asyncpg://…``);
``lib/medha_db.py`` converts to sync ``postgresql+psycopg2``, sets ``echo=False`` / ``pool_pre_ping=False``,
rewrites ``localhost`` → ``127.0.0.1`` by default (``MEDHA_PG_USE_IPV4=0`` to disable; helps Docker/macOS),
and adds libpq ``connect_timeout``. ``check_postgres_ready`` runs a **TCP probe**, then a **subprocess** that runs raw psycopg2 for ``SELECT 1`` + table check (forked Airflow workers can stall inside libpq/psycopg2; a fresh process matches ``uv run python scripts/smoke_medha_pg.py``).
Optional ``MEDHA_DATABASE_URL`` overrides the URL for Airflow-only runs.

**DAG tasks (monitor each in the UI):** ``prepare_config`` → ``validate_csv_source`` →
``check_postgres_ready`` → ``upsert_dhan_yahoo_map``. XCom carries path/config only (not CSV rows).

**Upsert task logging:** ``MEDHA_UPSERT_LOG_EVERY`` (INFO progress every N rows, default 500),
``MEDHA_UPSERT_LOG_EVERY_SEC`` (also log at least every N seconds, default 60; set ``0`` to disable time-based),
``MEDHA_UPSERT_LOG_API_TIMING=1`` (log per-row ``api_ms`` and ``db_execute_ms`` — very verbose on large CSVs).
**Upsert subprocess:** ``MEDHA_UPSERT_SUBPROCESS=1`` (default) runs the upsert in a fresh Python process so
``engine.begin()`` is not executed inside a forked Airflow worker (avoids the same hang as ``check_postgres_ready``).
Set ``MEDHA_UPSERT_SUBPROCESS=0`` to run in-process (may stall on macOS).
"""

from __future__ import annotations

import csv
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Variable
from sqlalchemy import MetaData

from lib.medha_db import (
    dhan_yahoo_instrument_map_table,
    medha_pg_healthcheck_subprocess,
    medha_pg_host_port,
    medha_pg_subprocess_timeout_seconds,
    medha_url_for_log,
    pg_connect_timeout_seconds,
    tcp_probe_host_port,
    use_ipv4_for_localhost,
)
from lib.dhan_yahoo_upsert_worker import _norm_header, run_upsert_from_cfg

log = logging.getLogger("airflow.task")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_csv_path() -> str:
    return str(_repo_root() / "dhan-Instrument List" / "stocks_and_index.csv")


def _default_yahoo_api_base() -> str:
    return os.environ.get("MEDHA_YAHOO_API_BASE_URL", "http://localhost:8000/api/yahoo-apis")


def _resolve_yahoo_api_base() -> str:
    return str(
        Variable.get(
            "medha_yahoo_api_base_url",
            default=_default_yahoo_api_base(),
        )
    ).rstrip("/")


def _resolve_csv_path() -> Path:
    env_csv = os.environ.get("MEDHA_DHAN_YAHOO_CSV_PATH")
    default_csv = _default_csv_path()
    csv_path = Variable.get(
        "medha_dhan_yahoo_csv_path",
        default=env_csv or default_csv,
    )
    return Path(csv_path).resolve()


def task_prepare_config(**context) -> dict:
    """Task 1: resolve CSV path, Yahoo API base, rate-limit delay (small XCom payload)."""
    log.info("Task=prepare_config phase=start")
    env_csv = os.environ.get("MEDHA_DHAN_YAHOO_CSV_PATH")
    default_csv = _default_csv_path()
    path = _resolve_csv_path()
    log.info(
        "Task=prepare_config csv: Variable medha_dhan_yahoo_csv_path | MEDHA_DHAN_YAHOO_CSV_PATH=%r "
        "default=%r → %s",
        env_csv,
        default_csv,
        path,
    )

    api_base = _resolve_yahoo_api_base()
    log.info(
        "Task=prepare_config yahoo_api: MEDHA_YAHOO_API_BASE_URL | Variable medha_yahoo_api_base_url → %r",
        api_base,
    )

    delay = float(os.environ.get("MEDHA_YAHOO_SEARCH_DELAY_SEC", "0") or "0")
    if delay > 0:
        log.info("Task=prepare_config MEDHA_YAHOO_SEARCH_DELAY_SEC=%s", delay)

    if not path.is_file():
        raise FileNotFoundError(
            f"CSV not found: {path}. Set Variable medha_dhan_yahoo_csv_path or "
            "MEDHA_DHAN_YAHOO_CSV_PATH, or place dhan-Instrument List/stocks_and_index.csv in the repo."
        )

    try:
        st = path.stat()
        log.info("Task=prepare_config csv_stat size_bytes=%s mtime=%s", st.st_size, st.st_mtime)
    except OSError as e:
        log.warning("Task=prepare_config could not stat CSV: %s", e)

    out = {
        "csv_path": str(path),
        "api_base": api_base,
        "delay_sec": delay,
    }
    log.info("Task=prepare_config phase=done xcom_keys=%s", list(out.keys()))
    return out


def task_validate_csv_source(**context) -> dict:
    """Task 2: headers + row count (streamed), format flag — does not load full file into XCom."""
    ti = context["ti"]
    cfg = ti.xcom_pull(task_ids="prepare_config")
    if not cfg or "csv_path" not in cfg:
        raise ValueError("task_validate_csv_source: missing XCom from prepare_config")
    path = Path(cfg["csv_path"])
    log.info("Task=validate_csv_source path=%s", path)

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row.")
        fieldnames = [_norm_header(h) for h in reader.fieldnames if h is not None]
        log.info(
            "Task=validate_csv_source headers count=%d sample=%s",
            len(fieldnames),
            fieldnames[:25],
        )
        total_rows = sum(1 for _ in reader)

    use_dhan_master = "EXCH_ID" in fieldnames
    log.info(
        "Task=validate_csv_source format=%s data_rows=%d",
        "dhan_master(EXCH_ID)" if use_dhan_master else "legacy_manual(dhan_*)",
        total_rows,
    )

    out = {
        **cfg,
        "total_rows": total_rows,
        "use_dhan_master": use_dhan_master,
        "header_count": len(fieldnames),
    }
    log.info("Task=validate_csv_source phase=done")
    return out


def task_check_postgres_ready(**context) -> dict:
    """Task 3: TCP probe + subprocess-isolated ``psycopg2`` ``SELECT 1`` + table existence."""
    _slow_connect_warn_s = 2.0
    max_attempts = max(1, int(os.environ.get("MEDHA_PG_CONNECT_RETRIES", "3") or "3"))
    retry_delay_s = float(os.environ.get("MEDHA_PG_CONNECT_RETRY_DELAY_SEC", "2") or "2")
    sub_t = medha_pg_subprocess_timeout_seconds()

    log.info("Task=check_postgres_ready phase=start")
    log.info(
        "Task=check_postgres_ready step=subprocess+psycopg2 (not in-process; avoids forked-worker stalls) "
        "connect_timeout=%ds (MEDHA_PG_CONNECT_TIMEOUT) subprocess_timeout=%ds (MEDHA_PG_SUBPROCESS_TIMEOUT)",
        pg_connect_timeout_seconds(),
        sub_t,
    )
    log.info(
        "Task=check_postgres_ready effective_dsn=%s "
        "(sync creds; localhost→127.0.0.1 when MEDHA_PG_USE_IPV4 is on)",
        medha_url_for_log(),
    )
    log.info(
        "Task=check_postgres_ready MEDHA_PG_USE_IPV4 effective=%s (localhost→127.0.0.1 when true; Docker/macOS)",
        use_ipv4_for_localhost(),
    )
    log.info(
        "Task=check_postgres_ready step=connect+SELECT_1 (max_attempts=%d retry_delay=%.1fs env MEDHA_PG_*)",
        max_attempts,
        retry_delay_s,
    )
    timeout_sec = pg_connect_timeout_seconds()
    probe_timeout = float(min(5.0, max(1.0, timeout_sec)))
    host, port = medha_pg_host_port()
    log.info(
        "=== Postgres: TCP probe to %s:%s (socket timeout %.1fs — fails fast if port unreachable) ===",
        host,
        port,
        probe_timeout,
    )
    try:
        tcp_probe_host_port(host, port, timeout=probe_timeout)
    except RuntimeError as e:
        log.error("=== Postgres: TCP probe FAILED — %s ===", e)
        raise
    log.info("=== Postgres: TCP probe SUCCEEDED — continuing to psycopg2 connect+SELECT 1 ===")

    log.info(
        "=== Postgres: CONNECTION TEST starting (libpq connect_timeout=%ds on psycopg2) ===",
        timeout_sec,
    )

    metadata = MetaData()
    table = dhan_yahoo_instrument_map_table(metadata)
    table_name = table.name

    for attempt in range(1, max_attempts + 1):
        t0 = time.monotonic()
        log.info(
            "=== Postgres: trying connection attempt %d/%d (SUCCESS or FAILED below) ===",
            attempt,
            max_attempts,
        )
        try:
            log.info(
                "Task=check_postgres_ready step=spawn subprocess (sys.executable=%r cwd=airflow) "
                "— next log line is after child exits",
                sys.executable,
            )
            medha_pg_healthcheck_subprocess(timeout_sec=sub_t)
            elapsed = time.monotonic() - t0
            log.info("Task=check_postgres_ready step=health_ok subprocess elapsed %.3fs", elapsed)
            if elapsed > _slow_connect_warn_s:
                log.warning(
                    "Task=check_postgres_ready slow subprocess: %.3fs (warn if >%.1fs)",
                    elapsed,
                    _slow_connect_warn_s,
                )
            log.info(
                "=== Postgres: CONNECTION TEST SUCCESS — SELECT 1 + table %r in %.3fs (attempt %d/%d) ===",
                table_name,
                elapsed,
                attempt,
                max_attempts,
            )
            log.info(
                "=== Postgres: SCHEMA CHECK SUCCESS — table %r exists (%d columns) — verified in subprocess ===",
                table.name,
                len(table.c),
            )
            break
        except RuntimeError as e:
            if "Alembic" in str(e) or "not found in schema public" in str(e):
                log.error("=== Postgres: SCHEMA CHECK FAILED — %s ===", e)
                raise
            if attempt < max_attempts:
                log.warning(
                    "=== Postgres: attempt %d/%d failed (will retry): %s ===",
                    attempt,
                    max_attempts,
                    e,
                )
                log.warning(
                    "Task=check_postgres_ready sleeping %.1fs before next attempt",
                    retry_delay_s,
                )
                time.sleep(retry_delay_s)
            else:
                log.error(
                    "=== Postgres: CONNECTION TEST FAILED after %d attempts: %s ===",
                    max_attempts,
                    e,
                )
                log.error(
                    "=== Postgres: FINAL — try: cd airflow && uv run python scripts/smoke_medha_pg.py ==="
                )
                raise
        except subprocess.TimeoutExpired as e:
            if attempt < max_attempts:
                log.warning(
                    "=== Postgres: attempt %d/%d subprocess timed out (will retry): %s ===",
                    attempt,
                    max_attempts,
                    e,
                )
                time.sleep(retry_delay_s)
            else:
                log.error(
                    "=== Postgres: subprocess timed out after %d attempts (MEDHA_PG_SUBPROCESS_TIMEOUT=%s) ===",
                    max_attempts,
                    os.environ.get("MEDHA_PG_SUBPROCESS_TIMEOUT", "<unset>"),
                )
                raise RuntimeError(
                    "Postgres health subprocess timed out; increase MEDHA_PG_SUBPROCESS_TIMEOUT or fix DB reachability."
                ) from e

    log.info(
        "=== Postgres: ALL CHECKS PASSED (connection + table %r) — ready for upsert task ===",
        table_name,
    )
    return {"postgres_ok": True, "table": table_name}


def _run_dhan_yahoo_upsert_subprocess(cfg: dict) -> None:
    """Run ``lib/dhan_yahoo_upsert_worker.run_upsert_from_cfg`` in a fresh Python process (fork-safe DB)."""
    import tempfile

    # DAG path: …/airflow/dags/dhan_yahoo_instrument_map_load.py → parents[1] == …/airflow (not repo root).
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_dhan_yahoo_upsert.py"
    if not script.is_file():
        raise FileNotFoundError(f"Missing {script}")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(cfg, tf)
        cfg_path = tf.name
    try:
        log.info(
            "Task=upsert_dhan_yahoo_map subprocess MEDHA_UPSERT_SUBPROCESS=1 script=%s sys.executable=%r cwd=%s",
            script,
            sys.executable,
            root,
        )
        r = subprocess.run(
            [sys.executable, str(script), cfg_path],
            cwd=str(root),
        )
        if r.returncode != 0:
            raise RuntimeError(f"upsert worker exited with code {r.returncode}")
    finally:
        try:
            os.unlink(cfg_path)
        except OSError:
            pass


def task_upsert_dhan_yahoo_map(**context) -> None:
    """Task 4: read full CSV, Yahoo API per row, upsert (long-running).

    By default runs the heavy work in a **subprocess** (``MEDHA_UPSERT_SUBPROCESS=1``) so
    ``engine.begin()`` / libpq run in a fresh interpreter — same fork issue as ``check_postgres_ready``.
    set ``MEDHA_UPSERT_SUBPROCESS=0`` to run in-process (may hang on macOS Airflow workers).
    """
    ti = context["ti"]
    cfg = ti.xcom_pull(task_ids="validate_csv_source")
    if not cfg or "csv_path" not in cfg:
        raise ValueError("task_upsert_dhan_yahoo_map: missing XCom from validate_csv_source")

    path = Path(cfg["csv_path"])
    api_base = cfg["api_base"]
    delay = float(cfg.get("delay_sec") or 0)
    use_dhan_master = bool(cfg["use_dhan_master"])
    total_hint = int(cfg.get("total_rows") or 0)

    log.info(
        "Task=upsert_dhan_yahoo_map phase=start csv=%s use_dhan_master=%s total_rows_hint=%d api_base=%r",
        path,
        use_dhan_master,
        total_hint,
        api_base,
    )

    cfg_payload = {
        "csv_path": str(path),
        "api_base": api_base,
        "delay_sec": delay,
        "use_dhan_master": use_dhan_master,
        "total_rows_hint": total_hint,
    }
    use_sub = os.environ.get("MEDHA_UPSERT_SUBPROCESS", "1").lower() not in ("0", "false", "no")
    if use_sub:
        _run_dhan_yahoo_upsert_subprocess(cfg_payload)
        return

    run_upsert_from_cfg(cfg_payload)


with DAG(
    dag_id="medha_dhan_yahoo_instrument_map_load",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["medha", "dhan_yahoo", "etl"],
) as dag:
    prepare_config = PythonOperator(
        task_id="prepare_config",
        python_callable=task_prepare_config,
    )
    validate_csv_source = PythonOperator(
        task_id="validate_csv_source",
        python_callable=task_validate_csv_source,
    )
    check_postgres_ready = PythonOperator(
        task_id="check_postgres_ready",
        python_callable=task_check_postgres_ready,
    )
    upsert_dhan_yahoo_map = PythonOperator(
        task_id="upsert_dhan_yahoo_map",
        python_callable=task_upsert_dhan_yahoo_map,
    )

    prepare_config >> validate_csv_source >> check_postgres_ready >> upsert_dhan_yahoo_map
