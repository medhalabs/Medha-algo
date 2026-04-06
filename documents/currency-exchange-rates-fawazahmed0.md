## Goal

Fetch **currency exchange rates** from the public [fawazahmed0/exchange-api](https://github.com/fawazahmed0/exchange-api) project (served via jsDelivr and a Cloudflare fallback), then **persist** them in your Medha **Postgres** database using the same patterns as the rest of the backend: **SQLAlchemy (async)**, **Alembic** migrations, and optional **scripts** under `backend/scripts/`.

This document is a **step-by-step playbook**; it does not assume the implementation already exists in the repo.

---

## What the API provides

The upstream project documents a **CDN URL shape** and a **fallback** host ([README](https://github.com/fawazahmed0/exchange-api#readme)):

| Piece | Value |
| --- | --- |
| Primary | `https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{date}/{apiVersion}/{endpoint}` |
| Fallback | `https://{date}.currency-api.pages.dev/{apiVersion}/{endpoint}` |

- **`{date}`** — `latest` or `YYYY-MM-DD` (historical daily snapshots).
- **`{apiVersion}`** — e.g. `v1`.
- **Endpoints** — e.g. `currencies.json` (list codes), `currencies/{base}.json` (rates with that **base** currency).

Example (EUR base, latest):

- Primary: `https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/eur.json`
- Fallback: `https://latest.currency-api.pages.dev/v1/currencies/eur.json`

The README recommends implementing a **fallback**: if the jsDelivr request fails, retry the same path on `currency-api.pages.dev`.

Typical JSON shape for `currencies/{base}.json` (conceptual):

```json
{
  "date": "2026-04-05",
  "eur": {
    "usd": 1.08,
    "inr": 92.5
  }
}
```

Exact keys may vary; your fetch code should read the documented structure from a live response and map it into rows.

---

## Prerequisites

- **Postgres** running and a `DATABASE_URL` the backend already uses (see [medha-yahoo-calendar-pipeline-from-scratch.md](./medha-yahoo-calendar-pipeline-from-scratch.md) §2 for async URL format).
- **`uv`** and the backend dependencies installed (`uv sync` from repo root or `backend/`).
- **Alembic** at `head` before you add new tables (or plan a new migration on top of current head).

---

## Step 1 — Decide what to store

Choose a **base currency** (e.g. `USD` or `INR`) and whether you need:

- **One row per (date, base, quote)** with a numeric rate, or  
- **One JSON blob per (date, base)** if you want every quote in a single column.

For analytics and indexing, **normalized rows** are usually easier:

| Column | Purpose |
| --- | --- |
| `rate_date` | Business date of the rate (`date` from API or the date you requested). |
| `base_currency` | ISO code you requested (e.g. `USD`). |
| `quote_currency` | ISO code (e.g. `EUR`, `INR`). |
| `rate` | Numeric factor (base → quote). |
| `fetched_at` | When your server stored the row (audit). |

Add a **unique constraint** on `(rate_date, base_currency, quote_currency)` so daily syncs can **upsert** safely.

---

## Step 2 — Add a SQLAlchemy model

1. Create a module under `backend/app/models/` (e.g. `currency_exchange_rate.py`) defining a `DeclarativeBase` model that matches the table above.  
2. Re-export the model from `backend/app/models/__init__.py` like the other models.

Use the same **`Base`** as the rest of the app (`from app.core.db import Base`) so Alembic’s `target_metadata` picks it up if your `env.py` imports all models.

---

## Step 3 — Create an Alembic migration

From repo root:

```bash
uv run --directory backend alembic revision -m "currency_exchange_rates"
```

Edit the new revision to `op.create_table(...)` with your columns, indexes, and the unique constraint. Then apply:

```bash
uv run --directory backend alembic upgrade head
```

Verify in Postgres that the table exists (`\dt` in `psql` or your GUI).

---

## Step 4 — Implement HTTP fetch with fallback

Use **`httpx`** (or the same HTTP client pattern used elsewhere in the project) to:

1. Build the primary URL:  
   `https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{base}.json`  
   (lowercase `base` is typical for this API; confirm against a live response.)
2. On network/HTTP failure or timeout, build the fallback URL:  
   `https://latest.currency-api.pages.dev/v1/currencies/{base}.json`
3. Parse JSON, iterate quote currencies and rates, and skip invalid or self-pairs if needed.

Keep timeouts short (e.g. 10–30 seconds) and log which URL succeeded.

Optional: support **historical** sync by passing `YYYY-MM-DD` instead of `latest` in both URL patterns for backfills.

---

## Step 5 — Upsert into the database

In an **async** function that receives `AsyncSession`:

1. **Delete** existing rows for the same `(rate_date, base_currency)` before insert, **or** use PostgreSQL **`INSERT ... ON CONFLICT DO UPDATE`** if you prefer true upserts.
2. Insert one row per quote currency.
3. `await session.commit()` (or use a transaction boundary consistent with your other scripts).

Reuse `get_session_factory()` from `app.core.db` the same way `scripts/sync_yahoo_calendar_to_db.py` does.

---

## Step 6 — Script entry point (manual and cron-friendly)

Add something like `backend/scripts/sync_currency_rates_to_db.py` that:

1. Loads `backend/.env` via your existing `get_settings()` / config pattern.
2. Parses CLI args: `--base USD`, optional `--date latest` or `--date 2026-04-05`.
3. Calls fetch → upsert → exits 0 on success.

Example invocation from repo root:

```bash
uv run --directory backend python scripts/sync_currency_rates_to_db.py --base USD
```

Document any env vars you add (e.g. default base currency) at the top of the script docstring, matching `sync_yahoo_calendar_to_db.py`.

---

## Step 7 — Schedule (optional)

- **Cron** on a server: run the script daily after market close or at a fixed UTC time.  
- **Airflow**: add a DAG that runs the same command in the Airflow worker environment, with `DATABASE_URL` (sync driver if your Airflow code uses `psycopg2`) pointing at the same Postgres — mirror how other Medha pipelines are wired (see `airflow/README.md` if present).

---

## Step 8 — Verify

1. Run the script once; query the table for today’s `rate_date` and a few quotes.  
2. Run again; confirm **no duplicates** (or that upsert updates in place).  
3. Temporarily break DNS or block `cdn.jsdelivr.net` in a dev environment and confirm the **fallback** URL still populates data.

---

## Operational notes

- **No API key** is required for this public CDN API; still treat it as **best-effort** data for app features, not a regulatory feed.  
- **Rate limits**: the project advertises no strict limits, but avoid hammering the CDN; one daily job per base currency is usually enough.  
- **License**: upstream is [CC0-1.0](https://github.com/fawazahmed0/exchange-api/blob/main/LICENSE); keep attribution in internal docs if your policy requires it.

---

## Related docs in this repo

- [medha-yahoo-calendar-pipeline-from-scratch.md](./medha-yahoo-calendar-pipeline-from-scratch.md) — Postgres, `backend/.env`, Alembic, `uv run` patterns.  
- [api-db-pipeline-end-to-end-playbook.md](./api-db-pipeline-end-to-end-playbook.md) — broader API → DB pipeline context.
