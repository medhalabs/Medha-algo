# Backend

FastAPI service wrapping [DhanHQ-py](https://github.com/dhan-oss/DhanHQ-py) and [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance, **not** exchange-official data).

### Layout

- **`app/dhan_api/`** — all Dhan-related code: `trading/`, `data/`, `ws/` (REST under `/api/trading`, `/api/data`; WebSockets under `/ws`).
- **`app/yahoo_apis/`** — Yahoo Finance (`/api/yahoo-apis`).
- **`app/core/`**, **`app/deps.py`**, **`app/models/`** — shared config, DB, dependencies.

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

## Commands

Prefer the **repo root** (see root `README.md`) with `uv run --directory backend …`.

From this folder:

```bash
uv sync          # if using a uv workspace, run `uv sync` from repo root instead
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```
