"""
Daily Yahoo Finance calendar → Postgres (four tables: ``yahoo_calendar_earnings``, ``yahoo_calendar_economic_events``,
``yahoo_calendar_splits``, ``yahoo_calendar_ipo``).

**Flow:** ``check_postgres`` → four separate blocks (one task per calendar kind):

- ``sync_calendar_earnings``
- ``sync_calendar_economic_events``
- ``sync_calendar_splits``
- ``sync_calendar_ipo``

Each task runs ``backend/scripts/sync_yahoo_calendar_to_db.py --calendar-type <kind>`` via subprocess
(same fork-safety pattern as Dhan↔Yahoo upsert).

**Schedule:** ``0 6 * * *`` (06:00 in the Airflow scheduler’s default timezone — often UTC unless you set
``AIRFLOW__CORE__DEFAULT_TIMEZONE`` to e.g. ``Asia/Kolkata``).

**Database:** Same as FastAPI — ``DATABASE_URL`` in ``backend/.env`` (``lib/medha_db.py`` loads it).

**Sync script env:** ``MEDHA_CALENDAR_TZ`` (default ``Asia/Kolkata``), ``MEDHA_CALENDAR_DAYS`` (default ``14``),
``MEDHA_CALENDAR_LIMIT`` (default ``500``), ``MEDHA_CALENDAR_FORCE`` (optional cache bust).

**Smoke (no Airflow):**
  ``cd airflow && uv run python scripts/smoke_yahoo_calendar_pg.py``

**One calendar from shell:**
  ``uv run --directory backend python scripts/sync_yahoo_calendar_to_db.py -t splits``
"""

from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

log = logging.getLogger("airflow.task")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _airflow_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def task_check_postgres(**context) -> None:
    """TCP probe + subprocess smoke script (avoids forked-worker libpq stalls)."""
    root = _airflow_dir()
    script = root / "scripts" / "smoke_yahoo_calendar_pg.py"
    if not script.is_file():
        raise FileNotFoundError(f"Missing {script}")
    log.info("Task=check_postgres script=%s cwd=%s", script, root)
    r = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(root),
    )
    if r.returncode != 0:
        raise RuntimeError(f"smoke_yahoo_calendar_pg failed with code {r.returncode}")


def _run_calendar_sync(calendar_type: str):
    """Build a task callable that syncs one calendar kind."""

    def _task(**context) -> None:
        root = _repo_root()
        runner = _airflow_dir() / "scripts" / "run_yahoo_calendar_sync.py"
        if not runner.is_file():
            raise FileNotFoundError(f"Missing {runner}")
        log.info(
            "Task=sync_calendar_%s runner=%s repo_root=%s",
            calendar_type,
            runner,
            root,
        )
        r = subprocess.run(
            [sys.executable, str(runner), "--calendar-type", calendar_type],
            cwd=str(root),
        )
        if r.returncode != 0:
            raise RuntimeError(
                f"run_yahoo_calendar_sync {calendar_type} exited with code {r.returncode}"
            )

    return _task


with DAG(
    dag_id="medha_yahoo_calendar_sync",
    start_date=datetime(2024, 1, 1),
    schedule="0 6 * * *",
    catchup=False,
    tags=["medha", "yahoo", "calendar", "etl"],
) as dag:
    check_postgres = PythonOperator(
        task_id="check_postgres",
        python_callable=task_check_postgres,
    )
    sync_calendar_earnings = PythonOperator(
        task_id="sync_calendar_earnings",
        python_callable=_run_calendar_sync("earnings"),
    )
    sync_calendar_economic_events = PythonOperator(
        task_id="sync_calendar_economic_events",
        python_callable=_run_calendar_sync("economic_events"),
    )
    sync_calendar_splits = PythonOperator(
        task_id="sync_calendar_splits",
        python_callable=_run_calendar_sync("splits"),
    )
    sync_calendar_ipo = PythonOperator(
        task_id="sync_calendar_ipo",
        python_callable=_run_calendar_sync("ipo"),
    )

    (
        check_postgres
        >> sync_calendar_earnings
        >> sync_calendar_economic_events
        >> sync_calendar_splits
        >> sync_calendar_ipo
    )
