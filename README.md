# Medha algo

Monorepo layout:

- **`backend/`** — FastAPI + DhanHQ-py + Postgres (uv workspace member).
- **`airflow/`** — Apache Airflow (separate `uv` project) for scheduled DAGs; see [`airflow/README.md`](airflow/README.md).
- **`frontend/`** — reserved for a future UI (not created yet).

## Postgres (Docker, port 5454)

```bash
docker compose up -d postgres
```

Defaults: user `medha`, password `medha`, database `medha_algo`. Use the `DATABASE_URL` in `backend/.env.example` or override in `docker-compose.yml` / `.env`.

## From the repo root

```bash
uv sync
cp backend/.env.example backend/.env   # set DATABASE_URL; add Dhan vars for the API
uv run --directory backend alembic upgrade head
uv run --directory backend uvicorn app.main:app --reload
```

Alembic only needs **`DATABASE_URL`** in `backend/.env` (Dhan credentials are not required to run migrations).

## From `backend/` only

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

If `uv sync` in `backend/` complains about the workspace, run **`uv sync` from the repo root** once so the root `uv.lock` and `.venv` are created.
