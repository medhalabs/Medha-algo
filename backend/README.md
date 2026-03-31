# Backend

FastAPI service wrapping [DhanHQ-py](https://github.com/dhan-oss/DhanHQ-py) and [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance, **not** exchange-official data).

### Layout

- **`app/dhan_api/`** — all Dhan-related code: `trading/`, `data/`, `ws/` (REST under `/api/trading`, `/api/data`; WebSockets under `/ws`).
- **`app/yahoo_apis/`** — Yahoo Finance (`/api/yahoo-apis`).
- **`app/core/`**, **`app/deps.py`**, **`app/models/`** — shared config, DB, dependencies.

### Database: Dhan ↔ Yahoo mapping

Table **`dhan_yahoo_instrument_map`** links Dhan instrument fields (`SECURITY_ID`, `EXCH_ID`, `UNDERLYING_SYMBOL`, `SYMBOL_NAME`, `DISPLAY_NAME`, `ISIN`) to **`yahoo_symbol`** (e.g. `INFY.NS` for NSE, `INFY.BO` for BSE).

- **Natural key:** `(dhan_exch_id, dhan_segment, dhan_underlying_symbol)` — one row per listing (same ticker on NSE vs BSE is two rows).
- **Optional:** `dhan_security_id` (unique when set) for direct Dhan API calls.
- **Pipeline use:** resolve this row → call Dhan with `security_id` / segment fields → call Yahoo with `yahoo_symbol`.

Apply migrations: `uv run --directory backend alembic upgrade head`.

**Adding rows**

1. **SQL (psql, DBeaver, etc.)** — connect with the same URL as `DATABASE_URL`, then:

```sql
INSERT INTO dhan_yahoo_instrument_map (
  dhan_exch_id, dhan_segment, dhan_underlying_symbol,
  dhan_symbol_name, dhan_display_name, dhan_security_id, isin,
  yahoo_symbol, mapping_source
) VALUES (
  'NSE', 'E', 'INFY',
  'INFOSYS LIMITED', 'Infosys', 1594, 'INE009A01021',
  'INFY.NS', 'manual'
);
```

2. **Example Python script** (uses your `.env` and SQLAlchemy):

```bash
uv run --directory backend python scripts/insert_mapping_example.py
```

3. **Later:** add REST endpoints or a CSV import job in the API to bulk-load from `stocks_and_index.csv`.

### Yahoo Finance (`/api/yahoo-apis`)

- `GET /api/yahoo-apis/ticker/{symbol}/info` — e.g. `RELIANCE.NS`, `^NSEI`
- `GET /api/yahoo-apis/ticker/{symbol}/history` — query: `period`, `interval`, `start`, `end`, …
- `GET /api/yahoo-apis/ticker/{symbol}/dividends|splits|actions`
- `GET /api/yahoo-apis/download?symbols=RELIANCE.NS,TCS.NS` — batch OHLCV (`format: split` JSON)
- `GET /api/yahoo-apis/search?q=reliance` — Yahoo symbol search

No extra env vars; calls run in a thread pool so the event loop stays responsive.

## Setup

```bash
cp .env.example .env
```

- **Migrations (Alembic):** set **`DATABASE_URL`** only (`postgresql+asyncpg://...`).
- **Running the API:** also set **`DHAN_CLIENT_ID`** and **`DHAN_ACCESS_TOKEN`**.

### Postgres (Docker) and `password authentication failed`

Use **`127.0.0.1`** in **`DATABASE_URL`** (see `.env.example`), not **`localhost`**, so clients hit the same IPv4 path as Docker’s published port (`5454:5432`). On macOS, **`localhost`** can use IPv6 (`::1`) and confuse debugging.

If the password in `.env` does not match the database (e.g. the data volume was created under different `POSTGRES_PASSWORD`), reset the user **inside** the container:

```bash
docker exec -it medha-postgres psql -U medha -d medha_algo -c "ALTER USER medha WITH PASSWORD 'medha';"
```

Or recreate the volume (⚠️ **destroys data**): `docker compose down`, remove the `medha_pgdata` volume, then `docker compose up -d` so `POSTGRES_PASSWORD` from `docker-compose.yml` applies on first init.

## Commands

Prefer the **repo root** (see root `README.md`) with `uv run --directory backend …`.

From this folder:

```bash
uv sync          # if using a uv workspace, run `uv sync` from repo root instead
uv run alembic upgrade head
uv run python scripts/db/upgrade_schema.py --revision head
uv run uvicorn app.main:app --reload
```
