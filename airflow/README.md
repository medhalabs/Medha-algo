# Medha Airflow

Apache Airflow **3.1.8** for **scheduled pipelines** (ETL, backfills). This is **separate** from `backend/` (FastAPI): own `uv` project and virtualenv at `airflow/.venv`.

Documentation for this version: [Apache Airflow 3.1.8](https://airflow.apache.org/docs/apache-airflow/3.1.8/).

## Install

From this directory:

```bash
cd airflow
uv sync
```

## Dependency lock (Airflow constraints)

Reproducible installs follow the [official constraint files](https://airflow.apache.org/docs/apache-airflow/stable/installation/installing-from-pypi.html). This repo vendors **`constraints-airflow-3.1.8-py312.txt`** (same content as the upstream `constraints-3.12.txt` for that release).

When you change dependencies and run **`uv lock`**, run it with:

```bash
cd airflow
UV_CONSTRAINT=constraints-airflow-3.1.8-py312.txt uv lock
```

Day-to-day **`uv sync`** uses the existing `uv.lock` and does not need that variable.

## Always set `AIRFLOW_HOME`

Use a **project-local** home so Airflow does not read another install’s config (e.g. `~/.airflow`):

```bash
export AIRFLOW_HOME="$(pwd)/airflow_home"
```

Add that line to your shell when working in this folder, or use the snippet below once per machine.

## First-time setup (metadata DB + config)

```bash
cd airflow
export AIRFLOW_HOME="$(pwd)/airflow_home"
uv sync
uv run airflow db migrate
# Point DAG folder at this repo’s tracked `dags/` (not under AIRFLOW_HOME)
rm -rf "$AIRFLOW_HOME/dags"
ln -s "$(pwd)/dags" "$AIRFLOW_HOME/dags"
uv run python -c "
from pathlib import Path
import os
import secrets

p = Path(os.environ['AIRFLOW_HOME']) / 'airflow.cfg'
t = p.read_text()
t = t.replace('load_examples = True', 'load_examples = False')
# Airflow 3: execution API / api-server workers require a shared JWT secret (not auto-filled in worker processes).
if 'jwt_secret' not in t:
    t = t.rstrip() + (
        '\n\n[api_auth]\n'
        '# Required for API + task execution JWT; keep stable across restarts.\n'
        f'jwt_secret = {secrets.token_urlsafe(32)}\n'
    )
p.write_text(t)
"
```

- Metadata DB defaults to **SQLite** at `airflow_home/airflow.db` (dev-friendly, gitignored).
- `airflow_home/` is **gitignored**; each clone runs the steps above once.
- Edit DAG files in **`airflow/dags/`** (symlinked into `AIRFLOW_HOME/dags`).

### Upgrading from Airflow 2.x

If you already have an older metadata DB under `airflow_home/`, run **`uv run airflow db migrate`** once after upgrading packages (same command as `airflow db init` replacement for applying migrations).

## Run a DAG once (smoke test)

```bash
export AIRFLOW_HOME="$(pwd)/airflow_home"
uv run airflow dags test example_medha_hello 2024-01-01
```

## DAG: load Dhan ↔ Yahoo map (`medha_dhan_yahoo_instrument_map_load`)

**Default input:** repo file **`dhan-Instrument List/stocks_and_index.csv`** (Dhan master). With **`EXCH_ID`** in the header, the DAG keeps **listed equities** (`INSTRUMENT=EQUITY`, `INSTRUMENT_TYPE=ES`) and **indices** (`INSTRUMENT=INDEX`). For each kept row it calls the **FastAPI Yahoo search** endpoint:

`GET {base}/search?q=<compact_underlying>.NS|.BO&max_results=1`

where **`NSE` → `.NS`** and **`BSE` → `.BO`**. A row is **upserted** only if the JSON response is a non-empty list and the first quote’s **`symbol`** matches the expected ticker. **Indices** that return no match for `NIFTY.NS`-style queries get a second search using the mapped `^` Yahoo symbol (same API) when listed in the DAG’s index map.

**Base URL:** env **`MEDHA_YAHOO_API_BASE_URL`** (default `http://localhost:8000/api/yahoo-apis`) or Airflow Variable **`medha_yahoo_api_base_url`**. The backend must be reachable from Airflow. Optional **`MEDHA_YAHOO_SEARCH_DELAY_SEC`** adds a sleep between calls (rate limiting).

If **`EXCH_ID`** is absent, the file is treated as a **legacy** CSV (`dhan_exch_id`, `dhan_underlying_symbol`, …) and the same API check runs using **`EQUITY`** semantics.

**Prerequisites:** Postgres (migrations applied), and the **Medha API** running if you want rows to resolve. The task reads **`DATABASE_URL`** from **`../backend/.env`** (async URLs are converted to sync `postgresql+psycopg2`). Override with **`MEDHA_DATABASE_URL`** in the Airflow environment if workers do not see `backend/.env`.

The DAG uses an **explicit table definition** (no `metadata.reflect`). Postgres access uses the same **`DATABASE_URL`** as the backend (from **`backend/.env`**, converted to sync **`postgresql+psycopg2`** in `lib/medha_db.py`). By default **`localhost` is rewritten to `127.0.0.1`** for the Airflow sync engine (`MEDHA_PG_USE_IPV4=0` keeps `localhost`). This avoids long hangs with **Docker Desktop on macOS** when `localhost` resolves to IPv6 first. **`check_postgres_ready`** also runs a **TCP socket probe** before psycopg2, then uses **`MEDHA_PG_CONNECT_TIMEOUT`** (default 10s), **`MEDHA_PG_CONNECT_RETRIES`** (default 3), and **`MEDHA_PG_CONNECT_RETRY_DELAY_SEC`** (default 2). Optional **`MEDHA_DATABASE_URL`** overrides the URL for Airflow-only environments.

**Optional overrides:** **`medha_dhan_yahoo_csv_path`** / **`MEDHA_DHAN_YAHOO_CSV_PATH`** for a different CSV.

Smoke-test Postgres the same way as **`check_postgres_ready`** (TCP probe, `SELECT 1`, table exists) without running Airflow:

```bash
cd airflow && uv run python scripts/smoke_medha_pg.py
```

To force **`localhost`** (disable IPv4 rewrite), the variable must apply to **Python**, not `cd`:  
`cd airflow && MEDHA_PG_USE_IPV4=0 uv run python scripts/smoke_medha_pg.py`  
Do **not** use `MEDHA_PG_USE_IPV4=0 cd airflow` — in the shell that only sets the var for `cd`, so the smoke script still sees the default.

If **DBeaver works** but the smoke script says **password authentication failed**: (1) Your **`DATABASE_URL`** in **`backend/.env`** must match the password Postgres actually has for that user (see smoke output: `password_len`). (2) If you had exported a bad URL, run `unset DATABASE_URL` and `unset MEDHA_DATABASE_URL` on **separate lines** (do not paste shell comments on the same line as `unset` in zsh). **`lib/medha_db.py`** loads **`backend/.env` with `override=True`** so the file wins over the shell when set.

```bash
cd airflow
export AIRFLOW_HOME="$(pwd)/airflow_home"
uv run airflow dags test medha_dhan_yahoo_instrument_map_load 2024-01-01
```

The DAG runs four tasks in order: **`prepare_config`** (paths/API base) → **`validate_csv_source`** (headers + row count) → **`check_postgres_ready`** (`SELECT 1` + table model) → **`upsert_dhan_yahoo_map`** (Yahoo API + DB). Check task-level logs to see where time is spent.

`schedule` is **`None`** (trigger manually or from the UI); change it in the DAG file when you want a fixed cadence.

## Dev UI: `airflow standalone`

Initializes the DB if needed, creates an admin user, and starts scheduler + API/UI (password printed once):

```bash
cd airflow
export AIRFLOW_HOME="$(pwd)/airflow_home"
uv run airflow standalone
```

Open **http://localhost:8080** (API server binds `0.0.0.0:8080`). `standalone` forces **SimpleAuthManager** (even if `airflow.cfg` says `FabAuthManager`).

**Login:** username **`admin`**. Password is **not** the literal `admin` string from the default `admin:admin` user list (the second token is the **role**). The password is the random string stored in **`airflow_home/simple_auth_manager_passwords.json.generated`** under the `"admin"` key. On the first run, Airflow prints it once; after that it only points to that file, so copy the value from the JSON. A copy of the same password may live in **`airflow_home/standalone_admin_password.txt`** when kept in sync.

**If login still fails:** wait out auth rate limits (defaults are strict), then retry. To **reset** the dev password, stop standalone, delete **`simple_auth_manager_passwords.json.generated`**, start again, and use the newly printed password.

**Run the pipeline without the UI** (scheduler must be running, e.g. standalone):

```bash
export AIRFLOW_HOME="$(pwd)/airflow_home"
uv run airflow dags unpause medha_dhan_yahoo_instrument_map_load
uv run airflow dags trigger medha_dhan_yahoo_instrument_map_load
```

Or run all tasks in one process (no web UI):

```bash
uv run airflow dags test medha_dhan_yahoo_instrument_map_load 2024-01-01
```

Run commands from the **`airflow/`** directory so `uv run` uses **`airflow/.venv`**. If your shell has another venv active (for example a repo-root workspace), you may see a harmless uv warning about `VIRTUAL_ENV`; either ignore it or `deactivate` before running Airflow.

If **`ValueError: The value api_auth/jwt_secret must be set!`** appears, your `airflow.cfg` predates the snippet above — append **`[api_auth]`** with **`jwt_secret`** (or set **`AIRFLOW__API_AUTH__JWT_SECRET`** to a long random string) so all processes share the same key, then restart.

For running components separately (closer to production), see the [Quick Start](https://airflow.apache.org/docs/apache-airflow/stable/start.html) (`airflow api-server`, `airflow scheduler`, `airflow dag-processor`, etc.).

## Troubleshooting

- **`AirflowConfigException` / wrong config**: you likely ran Airflow **without** `AIRFLOW_HOME` pointing at this repo’s `airflow_home`. Always `export AIRFLOW_HOME="$(pwd)/airflow_home"` from the `airflow/` directory first.
- **`You need to migrate the database`**: run **`uv run airflow db migrate`** with the same Airflow version as in `pyproject.toml`.
- **`api_auth/jwt_secret must be set`**: add **`[api_auth]`** / **`jwt_secret`** as in the first-time setup snippet, or `export AIRFLOW__API_AUTH__JWT_SECRET='<long-random-string>'` before starting.
- **Port `8794` already in use**: another Airflow or log server is still running — stop the old **`standalone`** (Ctrl+C) or the process holding that port.
- **`AIRFLOW__CORE__XCOM_BACKEND=airflow.models.xcom.BaseXCom`** can be set if you must override a bad global default.

Many **`[webserver]` → `[api]`** lines in logs are **deprecation warnings** from an older `airflow.cfg`; you can run **`uv run airflow config update`** when you want Airflow to rewrite options for 3.x, or edit `airflow.cfg` over time.

## Next steps

- Add DAGs under `dags/` that call your backend (HTTP), `yfinance`, or `dhanhq` (install those deps here or use `uv add`, then re-lock with `UV_CONSTRAINT` as above).
- For production, use Postgres for Airflow metadata and a process manager / Docker for API server + scheduler + workers.
