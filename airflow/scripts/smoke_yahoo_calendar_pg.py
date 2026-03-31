#!/usr/bin/env python3
"""
Smoke-test Postgres for the Yahoo calendar sync DAG: TCP probe, SELECT 1, Yahoo calendar tables exist.

Run from repo:
  cd airflow && uv run python scripts/smoke_yahoo_calendar_pg.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_AIRFLOW_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_AIRFLOW_ROOT / "dags"))

from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from lib.medha_db import (  # noqa: E402
    backend_env_file,
    format_engine_for_log,
    get_medha_engine,
    pg_connect_timeout_seconds,
    tcp_probe_host_port,
    use_ipv4_for_localhost,
)


def main() -> int:
    print(
        "MEDHA_PG_USE_IPV4 env="
        f"{os.environ.get('MEDHA_PG_USE_IPV4', '<unset>')!r} "
        f"effective_rewrite_localhost={use_ipv4_for_localhost()}"
    )
    env_path = backend_env_file()
    print(f"backend/.env path: {env_path} exists={env_path.is_file()}")
    engine = get_medha_engine()
    print("effective_dsn:", format_engine_for_log(engine))
    host = engine.url.host or "127.0.0.1"
    port = int(engine.url.port or 5432)
    t = float(min(5.0, max(1.0, pg_connect_timeout_seconds())))
    print(f"tcp_probe {host}:{port} timeout={t}s ...")
    tcp_probe_host_port(host, port, timeout=t)
    print("tcp_probe OK")
    try:
        with engine.connect() as conn:
            one = conn.execute(text("SELECT 1")).scalar()
    except OperationalError as e:
        print("FAIL: psycopg2 connect — check DATABASE_URL in backend/.env.")
        print(e)
        return 1
    print("SELECT 1 =>", one)
    if one != 1:
        return 1
    required = (
        "yahoo_calendar_earnings",
        "yahoo_calendar_economic_events",
        "yahoo_calendar_splits",
        "yahoo_calendar_ipo",
    )
    insp = inspect(engine)
    for name in required:
        if not insp.has_table(name, schema="public"):
            print(
                f"FAIL: table {name} missing — run: cd backend && uv run alembic upgrade head"
            )
            return 1
        print(f"table {name} OK")
    print("ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
