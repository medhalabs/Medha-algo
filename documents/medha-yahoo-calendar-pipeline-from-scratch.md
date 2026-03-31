## Goal

Build the Medha Yahoo Calendar pipeline **end-to-end**, starting from an empty machine:

- Bring up **Postgres**
- Configure **backend** (`FastAPI` + Alembic)
- Create/upgrade the **DB schema**
- Verify the Yahoo Calendar tables exist
- Run the sync script manually (no Airflow)
- Run the **Airflow** DAG end-to-end (UI or CLI)
- Debug the common failures

This guide matches the current repo behavior:

- **Four** calendar kinds: `earnings`, `economic_events`, `splits`, `ipo`
- **Four** DB tables (one per kind):
  - `yahoo_calendar_earnings`
  - `yahoo_calendar_economic_events`
  - `yahoo_calendar_splits`
  - `yahoo_calendar_ipo`

---

## Prerequisites

- Docker Desktop (for Postgres container)
- `uv` installed (Python package manager used by this repo)
- Python 3.12 (what Airflow project is pinned to)

Repo layout:

- `backend/` — FastAPI + Alembic + SQLAlchemy (async DB URL)
- `airflow/` — Airflow project (sync DB URL via psycopg2)

---

## 1) Start Postgres (Docker)

From repo root:

```bash
docker compose up -d postgres
```

Defaults (from repo `README.md`):

- Host port: **5454**
- User: `medha`
- Password: `medha`
- DB: `medha_algo`

---

## 2) Create backend env file (`backend/.env`)

From repo root:

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and make sure **`DATABASE_URL`** is set.

Expected format for backend migrations and API (async):

```text
DATABASE_URL=postgresql+asyncpg://medha:medha@127.0.0.1:5454/medha_algo
```

Notes:

- Use **`127.0.0.1`**, not `localhost` (macOS can prefer IPv6 and confuse debugging).
- Alembic migrations only need `DATABASE_URL`. You do **not** need Dhan credentials to migrate.

---

## 3) Install dependencies

From repo root (recommended, since this is a uv workspace):

```bash
uv sync
```

If you only work inside `backend/`, you can also do:

```bash
cd backend
uv sync
```

---

## 4) Build / upgrade the database schema (Alembic)

Run migrations to the latest revision:

```bash
uv run --directory backend alembic upgrade head
```

Or from `backend/`:

```bash
cd backend
uv run alembic upgrade head
```

### If you previously had the old unified table (`yahoo_calendar_event`)

Older setups created a single table `yahoo_calendar_event`. Newer code uses four tables.

Running `alembic upgrade head` will apply a follow-up migration that:

- creates the four `yahoo_calendar_*` tables if missing
- copies rows out of `yahoo_calendar_event` into the right table by `calendar_type`
- drops `yahoo_calendar_event`

---

## 5) Verify the calendar tables exist (no Airflow)

Use the provided smoke script (runs the same checks as the Airflow DAG’s `check_postgres` task):

```bash
cd airflow
export AIRFLOW_HOME="$(pwd)/airflow_home"
uv run python scripts/smoke_yahoo_calendar_pg.py
```

Expected output includes:

- `SELECT 1 => 1`
- `table yahoo_calendar_earnings OK`
- `table yahoo_calendar_economic_events OK`
- `table yahoo_calendar_splits OK`
- `table yahoo_calendar_ipo OK`
- `ALL OK`

If it fails with “missing table …”, re-run:

```bash
uv run --directory backend alembic upgrade head
```

---

## 6) Run the calendar sync manually (no Airflow)

This fetches rows from yfinance and writes them to Postgres.

### Sync all four kinds

```bash
uv run --directory backend python scripts/sync_yahoo_calendar_to_db.py --calendar-type all
```

### Sync one kind (example: splits)

```bash
uv run --directory backend python scripts/sync_yahoo_calendar_to_db.py --calendar-type splits
```

### Useful environment overrides

The sync script reads these env vars:

- `MEDHA_CALENDAR_TZ` — default `Asia/Kolkata`
- `MEDHA_CALENDAR_DAYS` — default `14` (window end = today + N days)
- `MEDHA_CALENDAR_LIMIT` — default `500`
- `MEDHA_CALENDAR_FORCE` — set to `1` to pass `force=True` to yfinance (bypass cache when supported)

Example:

```bash
MEDHA_CALENDAR_DAYS=7 MEDHA_CALENDAR_LIMIT=200 \
uv run --directory backend python scripts/sync_yahoo_calendar_to_db.py --calendar-type earnings
```

---

## 7) Build + run the backend API (how to fetch data via HTTP)

The calendar **ETL** writes into Postgres using `backend/scripts/sync_yahoo_calendar_to_db.py`.
Separately, the backend exposes HTTP endpoints to **fetch Yahoo calendar data live** (without writing to DB).

### 7.1) What code serves the calendar endpoints

- **Routes**: `backend/app/yahoo_apis/routes/calendar.py`
- **Router mount**: `backend/app/yahoo_apis/router.py` (mounted under `/api/yahoo-apis`)
- **Implementation**: `backend/app/yahoo_apis/service.py` uses `yfinance.Calendars()`

### 7.2) Start the API server

From repo root:

```bash
uv run --directory backend uvicorn app.main:app --reload
```

### 7.3) Call the Yahoo calendar endpoints

Base path:

- `GET /api/yahoo-apis/calendar/...`

Endpoints:

- Earnings: `GET /api/yahoo-apis/calendar/earnings`
- Economic events: `GET /api/yahoo-apis/calendar/economic-events`
- Splits: `GET /api/yahoo-apis/calendar/splits`
- IPO: `GET /api/yahoo-apis/calendar/ipo`

Common query params:

- `start`: `YYYY-MM-DD` (optional)
- `end`: `YYYY-MM-DD` (optional)
- `limit`: default 12, max 500
- `offset`: default 0
- `force`: `true|false` (bypass yfinance cache when supported)

Earnings-only params:

- `market_cap` (optional)
- `filter_most_active` (default true)

Example calls (from another terminal):

```bash
curl "http://localhost:8000/api/yahoo-apis/calendar/earnings?start=2026-04-01&end=2026-04-14&limit=50"
curl "http://localhost:8000/api/yahoo-apis/calendar/economic-events?limit=25"
curl "http://localhost:8000/api/yahoo-apis/calendar/splits?start=2026-04-01&end=2026-04-30"
curl "http://localhost:8000/api/yahoo-apis/calendar/ipo?limit=50"
```

What you get back:

- JSON: a list of rows (schema varies by calendar kind; it is Yahoo’s/yfinance’s columns)

If you want to **persist** the same data to Postgres, use the sync script in section 6 (or the Airflow DAG in section 9).

---

## 8) Setup Airflow (first time only)

From `airflow/`:

```bash
cd airflow
export AIRFLOW_HOME="$(pwd)/airflow_home"
uv sync
uv run airflow db migrate
rm -rf "$AIRFLOW_HOME/dags"
ln -s "$(pwd)/dags" "$AIRFLOW_HOME/dags"
```

Then add the required Airflow 3 `jwt_secret` once (see `airflow/README.md` for the exact snippet).

---

## 9) Run the Airflow pipeline end-to-end

### Option A: with UI (dev)

```bash
cd airflow
export AIRFLOW_HOME="$(pwd)/airflow_home"
uv run airflow standalone
```

Open UI at `http://localhost:8080`, find DAG:

- `medha_yahoo_calendar_sync`

Trigger it manually and watch tasks:

- `check_postgres`
- `sync_calendar_earnings`
- `sync_calendar_economic_events`
- `sync_calendar_splits`
- `sync_calendar_ipo`

### Option B: run as a single-process test (no UI)

```bash
cd airflow
export AIRFLOW_HOME="$(pwd)/airflow_home"
uv run airflow dags test medha_yahoo_calendar_sync 2024-01-01
```

---

## 10) How the DAG actually runs (important)

`airflow/dags/yahoo_calendar_sync.py` does not call Python functions directly.
Each task runs a **subprocess**:

- `airflow/scripts/run_yahoo_calendar_sync.py` →
- `uv run --directory backend python backend/scripts/sync_yahoo_calendar_to_db.py --calendar-type <kind>`

This “fresh process” approach avoids macOS/Docker fork + libpq stalls that can happen if DB connections are created inside an Airflow worker process.

---

## 11) Troubleshooting

### A) DAG is “not building” (doesn’t show up in UI)

- Confirm `AIRFLOW_HOME` is set and DAGs are symlinked:

```bash
cd airflow
export AIRFLOW_HOME="$(pwd)/airflow_home"
ls -la "$AIRFLOW_HOME/dags"
```

It should be a symlink to `airflow/dags/`.

### B) `check_postgres` fails with “missing table yahoo_calendar_…”

This means migrations were not applied to the **same database URL** Airflow is using.

Fix:

```bash
uv run --directory backend alembic upgrade head
cd airflow && uv run python scripts/smoke_yahoo_calendar_pg.py
```

### C) “password authentication failed”

Most common causes:

- `backend/.env` has the wrong password / points at a different DB
- DB volume was initialized with a different password earlier

Fix password inside the container (example from `backend/README.md`):

```bash
docker exec -it medha-postgres psql -U medha -d medha_algo -c "ALTER USER medha WITH PASSWORD 'medha';"
```

### D) Airflow connects but backend migrations point elsewhere

Make sure you’re not accidentally overriding `DATABASE_URL` in your shell.

If needed, run:

```bash
unset DATABASE_URL
unset MEDHA_DATABASE_URL
```

Then rely on `backend/.env`.

### E) yfinance returns empty rows

Possible reasons:

- Weekend / no events in your selected window
- Too strict filters (earnings `market_cap`, etc.)
- Temporary Yahoo blocking/rate limiting

Try:

- Increase window days: `MEDHA_CALENDAR_DAYS=30`
- Use `MEDHA_CALENDAR_FORCE=1`

---

## 12) Checklist (copy/paste)

From repo root:

```bash
docker compose up -d postgres
cp backend/.env.example backend/.env
uv sync
uv run --directory backend alembic upgrade head
cd airflow
export AIRFLOW_HOME="$(pwd)/airflow_home"
uv sync
uv run airflow db migrate
uv run python scripts/smoke_yahoo_calendar_pg.py
uv run airflow dags test medha_yahoo_calendar_sync 2024-01-01
```

