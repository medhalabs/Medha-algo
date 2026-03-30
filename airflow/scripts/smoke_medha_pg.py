#!/usr/bin/env python3
"""
Smoke-test the same Postgres steps as ``check_postgres_ready`` (no Airflow).

Run from repo:
  cd airflow && uv run python scripts/smoke_medha_pg.py

To test with ``localhost`` unchanged (no 127.0.0.1 rewrite), the env var must apply to **Python**, not ``cd``:
  cd airflow && MEDHA_PG_USE_IPV4=0 uv run python scripts/smoke_medha_pg.py

Wrong (var only applies to ``cd``): ``MEDHA_PG_USE_IPV4=0 cd airflow && ...``

Exit 0 if TCP probe, SELECT 1, and table existence all pass; non-zero otherwise.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# airflow/scripts/ -> add .../airflow/dags to path
_AIRFLOW_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_AIRFLOW_ROOT / "dags"))

from sqlalchemy import MetaData, inspect, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from sqlalchemy.engine.url import make_url  # noqa: E402

from lib.medha_db import (  # noqa: E402
    backend_env_file,
    dhan_yahoo_instrument_map_table,
    format_engine_for_log,
    get_medha_engine,
    pg_connect_timeout_seconds,
    resolve_database_url,
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
    sync_url = resolve_database_url()
    u = make_url(sync_url)
    pw = u.password or ""
    print(
        f"parsed URL: user={u.username!r} host={u.host!r} port={u.port} database={u.database!r} "
        f"password_len={len(pw)}"
    )
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
        print("FAIL: psycopg2 connect — check DATABASE_URL password matches Postgres (see backend/.env).")
        print(e)
        return 1
    print("SELECT 1 =>", one)
    if one != 1:
        print("FAIL: expected 1")
        return 1
    md = MetaData()
    tbl = dhan_yahoo_instrument_map_table(md)
    if not inspect(engine).has_table(tbl.name, schema="public"):
        print(f"FAIL: table {tbl.name!r} missing in public")
        return 1
    print(f"table {tbl.name!r} OK")
    print("ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
