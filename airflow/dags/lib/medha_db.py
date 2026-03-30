"""Sync Postgres access for Airflow — same database as the FastAPI backend."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL, make_url
from sqlalchemy.pool import NullPool


def _backend_env_path() -> Path:
    """
    Resolve ``backend/.env`` whether DAGs live under ``airflow/dags/`` or a symlinked tree.
    Walks parents so a copied ``…/dags/lib/`` layout still finds the repo ``backend/.env``.
    """
    here = Path(__file__).resolve()
    for d in [here, *here.parents]:
        candidate = d / "backend" / ".env"
        if candidate.is_file():
            return candidate
    return here.parents[3] / "backend" / ".env"


def backend_env_file() -> Path:
    """Path to ``backend/.env`` (for logging / smoke tests)."""
    return _backend_env_path()


def normalize_sync_database_url(url: str) -> str:
    """Same ``DATABASE_URL`` as ``app.core.config`` (asyncpg) → sync ``postgresql+psycopg2://`` for Airflow."""
    u = url.strip().strip('"').strip("'")
    if u.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg2://" + u[len("postgresql+asyncpg://") :]
    if u.startswith("postgres://"):
        return "postgresql+psycopg2://" + u[len("postgres://") :]
    if u.startswith("postgresql+psycopg://"):
        return "postgresql+psycopg2://" + u[len("postgresql+psycopg://") :]
    return u


def resolve_database_url() -> str:
    """
    Load ``backend/.env`` (if present), then resolve URL in the same order as typical backend usage:

    1. ``MEDHA_DATABASE_URL`` — optional override when Airflow runs without repo-relative ``backend/.env``
    2. ``DATABASE_URL`` — same variable as FastAPI / Alembic (``postgresql+asyncpg://...``)

    The returned string is always a synchronous SQLAlchemy URL (``postgresql+psycopg2://...``).
    """
    env_file = _backend_env_path()
    if env_file.is_file():
        # Default load_dotenv(override=False) leaves stale DATABASE_URL from the shell wins over
        # backend/.env — same symptom as "DBeaver works, smoke test password failed".
        load_dotenv(env_file, override=True)

    raw = (os.environ.get("MEDHA_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if not raw:
        raise RuntimeError(
            "Set DATABASE_URL in backend/.env (same as the API), or MEDHA_DATABASE_URL for Airflow. "
            "Use postgresql+asyncpg://… in .env; this module converts it to psycopg2 for sync tasks."
        )
    return normalize_sync_database_url(raw)


def pg_connect_timeout_seconds() -> int:
    """TCP connect timeout for psycopg2 (libpq). Default 10s; override ``MEDHA_PG_CONNECT_TIMEOUT``."""
    return int(os.environ.get("MEDHA_PG_CONNECT_TIMEOUT", "10") or "10")


def use_ipv4_for_localhost() -> bool:
    """
    When True (default), rewrite host ``localhost`` → ``127.0.0.1`` for the sync Airflow engine.

    Docker Desktop on macOS often binds published ports on IPv4; ``localhost`` can resolve to ``::1``
    first and stall in ways libpq's ``connect_timeout`` does not cap. Set ``MEDHA_PG_USE_IPV4=0`` to
    keep hostname ``localhost`` unchanged.
    """
    return os.environ.get("MEDHA_PG_USE_IPV4", "1").lower() not in ("0", "false", "no")


def _airflow_sync_engine_url() -> URL:
    """
    Apply localhost→IPv4, libpq ``connect_timeout``, optional ``sslmode``.

    Passes a :class:`URL` into :func:`create_engine` — never ``str(URL)``, which masks passwords
    as ``***`` in SQLAlchemy 2 and would break authentication.
    """
    u = make_url(resolve_database_url())
    if use_ipv4_for_localhost() and (u.host or "").lower() == "localhost":
        u = u.set(host="127.0.0.1")
    timeout = pg_connect_timeout_seconds()
    q = dict(u.query) if u.query else {}
    if "connect_timeout" not in q:
        q["connect_timeout"] = str(timeout)
    sslmode = (os.environ.get("MEDHA_PG_SSLMODE") or "").strip()
    if sslmode and "sslmode" not in q:
        q["sslmode"] = sslmode
    return u.set(query=q)


def get_medha_engine() -> Engine:
    """
    Sync engine: same connection target as ``app.core.db`` — ``echo=False``, ``pool_pre_ping=False`` —
    with ``postgresql+psycopg2`` instead of asyncpg. Uses :class:`NullPool` so forked Airflow workers
    do not inherit a pooled connection from another process.

    ``pool_pre_ping`` is off: in some Airflow worker setups, checkout + ping can stall after fork.
    ``connect_timeout`` is set only on the URL query (libpq); avoid duplicating it in
    ``connect_args`` (can confuse some libpq builds).
    """
    return create_engine(
        _airflow_sync_engine_url(),
        echo=False,
        poolclass=NullPool,
        pool_pre_ping=False,
    )


def medha_url_for_log() -> str:
    """Log-safe DSN (password hidden) — same target as :func:`get_medha_engine`."""
    return _airflow_sync_engine_url().render_as_string(hide_password=True)


def medha_pg_host_port() -> tuple[str, int]:
    """Host and port for TCP probes (after localhost→IPv4 rewrite)."""
    u = _airflow_sync_engine_url()
    return (u.host or "127.0.0.1", int(u.port or 5432))


def medha_psycopg2_connect():
    """
    Direct ``psycopg2.connect`` with explicit kwargs (no SQLAlchemy).

    The ``check_postgres_ready`` task uses this for ``SELECT 1`` and schema checks. Some Airflow
    workers appear to block inside SQLAlchemy’s first pool checkout even with :class:`NullPool`;
    raw psycopg2 avoids that path entirely.
    """
    import psycopg2

    u = _airflow_sync_engine_url()
    kwargs = {
        "host": u.host or "127.0.0.1",
        "port": int(u.port or 5432),
        "user": u.username,
        "password": u.password or "",
        "dbname": u.database or "",
        "connect_timeout": pg_connect_timeout_seconds(),
    }
    q = dict(u.query) if u.query else {}
    if "sslmode" in q:
        kwargs["sslmode"] = q["sslmode"]
    return psycopg2.connect(**kwargs)


def medha_public_table_exists(conn, table_name: str) -> bool:
    """Return True if ``public.<table_name>`` exists (uses an existing psycopg2 connection)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            LIMIT 1
            """,
            ("public", table_name),
        )
        return cur.fetchone() is not None


def _airflow_dags_parent_dir() -> Path:
    """``…/airflow`` — parent of the ``dags`` package (``medha_db`` lives under ``dags/lib``)."""
    return Path(__file__).resolve().parents[2]


def medha_pg_subprocess_timeout_seconds() -> int:
    """Wall-clock timeout for :func:`medha_pg_healthcheck_subprocess` (``MEDHA_PG_SUBPROCESS_TIMEOUT``)."""
    ct = pg_connect_timeout_seconds()
    default_timeout = max(45, ct + 15)
    raw = (os.environ.get("MEDHA_PG_SUBPROCESS_TIMEOUT") or "").strip()
    wall = int(raw) if raw else default_timeout
    return max(wall, ct + 5)


def medha_pg_healthcheck_subprocess(*, timeout_sec: int | None = None) -> None:
    """
    Run ``SELECT 1`` + ``information_schema`` table check in a **new Python process**.

    Airflow task workers are often forked from a long-lived parent; ``psycopg2`` / libpq can
    block indefinitely in that context even when the same code works from a shell. A subprocess
    matches the shell case and lets us enforce ``subprocess``'s wall-clock timeout.

    Wall-clock timeout: ``timeout_sec`` if given, else :func:`medha_pg_subprocess_timeout_seconds`.
    """
    root = _airflow_dags_parent_dir()
    env = os.environ.copy()
    env["MEDHA_PG_HEALTHCHECK_ROOT"] = str(root.resolve())
    ct = pg_connect_timeout_seconds()
    wall = medha_pg_subprocess_timeout_seconds() if timeout_sec is None else timeout_sec
    wall = max(wall, ct + 5)
    code = """import os, sys
from pathlib import Path
root = Path(os.environ["MEDHA_PG_HEALTHCHECK_ROOT"])
sys.path.insert(0, str(root / "dags"))
from sqlalchemy import MetaData
from lib.medha_db import (
    dhan_yahoo_instrument_map_table,
    medha_psycopg2_connect,
    medha_public_table_exists,
)
with medha_psycopg2_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        if cur.fetchone()[0] != 1:
            raise SystemExit(2)
    md = MetaData()
    t = dhan_yahoo_instrument_map_table(md)
    if not medha_public_table_exists(conn, t.name):
        raise SystemExit(3)
print("MEDHA_PG_HEALTH_OK")
"""
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=wall,
    )
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if r.returncode == 3:
        raise RuntimeError(
            "Table dhan_yahoo_instrument_map not found in schema public — run Alembic migrations "
            "(cd backend && uv run alembic upgrade head)."
        )
    if r.returncode != 0:
        msg = err or out or f"exit {r.returncode}"
        raise RuntimeError(f"Postgres health subprocess failed (code {r.returncode}): {msg}")
    if "MEDHA_PG_HEALTH_OK" not in out:
        raise RuntimeError(f"Postgres health subprocess unexpected stdout: {out!r}")


def tcp_probe_host_port(host: str, port: int, *, timeout: float) -> None:
    """
    Strict socket-level connect with ``timeout`` (seconds). Fails fast when the port is black-holed,
    which libpq sometimes does not treat the same as ``connect_timeout``.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as e:
        raise RuntimeError(
            f"TCP probe failed to {host!r}:{port} within {timeout}s: {e}"
        ) from e


def format_engine_for_log(engine: Engine) -> str:
    """Log-safe DSN (password hidden)."""
    return engine.url.render_as_string(hide_password=True)


def dhan_yahoo_instrument_map_table(metadata: MetaData) -> Table:
    """
    Declarative schema for ``dhan_yahoo_instrument_map`` — avoids ``metadata.reflect()``.
    Keep in sync with Alembic / ``app.models.dhan_yahoo_map.DhanYahooInstrumentMap``.
    """
    return Table(
        "dhan_yahoo_instrument_map",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("dhan_security_id", BigInteger, nullable=True),
        Column("isin", String(32), nullable=True),
        Column("dhan_exch_id", String(8), nullable=False),
        Column("dhan_segment", String(16), nullable=False),
        Column("dhan_underlying_symbol", String(128), nullable=False),
        Column("dhan_symbol_name", Text, nullable=True),
        Column("dhan_display_name", Text, nullable=True),
        Column("yahoo_symbol", String(64), nullable=False),
        Column("mapping_source", String(32), nullable=True),
        Column("is_active", Boolean, nullable=False),
        Column("notes", Text, nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=True),
        Column("updated_at", DateTime(timezone=True), nullable=True),
        UniqueConstraint(
            "dhan_exch_id",
            "dhan_segment",
            "dhan_underlying_symbol",
            name="uq_dhan_yahoo_dhan_symbol_exch_seg",
        ),
    )
