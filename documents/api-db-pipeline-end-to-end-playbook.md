# API + DB + Pipeline End-to-End Playbook

Use this as your reusable blueprint whenever you build a new data feature.

---

## What You Are Building

For any new feature, you build 4 layers:

1. **API layer** (FastAPI route)  
   Exposes data as JSON.
2. **DB layer** (SQLAlchemy model + Alembic migration)  
   Stores data in Postgres.
3. **Pipeline layer** (sync script)  
   Fetches/transforms data and writes to DB.
4. **Scheduler layer** (Airflow DAG, optional)  
   Runs pipeline automatically.

If you follow this order, development stays simple and predictable.

---

## 0) Start with a mini spec (important)

Before writing code, write this in plain English:

- **Feature name**: e.g. "symbol sentiment"
- **Source**: external API/file/computation
- **DB columns**: exact fields and types
- **API endpoint**: URL + query params + response shape
- **Refresh behavior**: one-time, hourly, daily?
- **Idempotency rule**: what rows get replaced on rerun?

Example mini spec:

- Store daily sentiment score for each symbol.
- Table columns: `symbol`, `date`, `score`, `source`, `created_at`.
- API: `GET /api/custom/sentiment/{symbol}?start=...&end=...`
- Pipeline: daily run, replace rows for same `(symbol, date window)`.

---

## 1) Project setup (Medha repo)

From repo root:

```bash
docker compose up -d postgres
cp backend/.env.example backend/.env
uv sync
```

Check `backend/.env` has:

```text
DATABASE_URL=postgresql+asyncpg://medha:medha@127.0.0.1:5454/medha_algo
```

Use `127.0.0.1` over `localhost` to avoid IPv6 confusion on macOS/Docker.

---

## 2) Create DB model first

Create a model file in `backend/app/models/`.

Example:

```python
# backend/app/models/symbol_sentiment.py
from datetime import date, datetime
from sqlalchemy import String, Date, DateTime, Float, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class SymbolSentiment(Base):
    __tablename__ = "symbol_sentiment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

Register it in:

- `backend/app/models/__init__.py`
- (if needed) import in `backend/alembic/env.py` so Alembic metadata sees it

---

## 3) Create Alembic migration

Generate:

```bash
cd backend
uv run alembic revision -m "add symbol_sentiment table"
```

Edit generated file in `backend/alembic/versions/...`:

```python
def upgrade() -> None:
    op.create_table(
        "symbol_sentiment",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_symbol_sentiment_symbol", "symbol_sentiment", ["symbol"])
    op.create_index("ix_symbol_sentiment_day", "symbol_sentiment", ["day"])


def downgrade() -> None:
    op.drop_index("ix_symbol_sentiment_day", table_name="symbol_sentiment")
    op.drop_index("ix_symbol_sentiment_symbol", table_name="symbol_sentiment")
    op.drop_table("symbol_sentiment")
```

Apply:

```bash
uv run --directory backend alembic upgrade head
```

Verify migration status:

```bash
uv run --directory backend alembic current
```

---

## 4) Build API route to read data

Add route under your module (example structure):

- `backend/app/yahoo_apis/routes/sentiment.py`
- include in `backend/app/yahoo_apis/router.py`

Example route:

```python
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models.symbol_sentiment import SymbolSentiment

router = APIRouter()


@router.get("/{symbol}")
async def get_sentiment(
    symbol: str,
    start: date | None = Query(None),
    end: date | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="start cannot be after end")

    stmt = select(SymbolSentiment).where(SymbolSentiment.symbol == symbol)
    if start:
        stmt = stmt.where(SymbolSentiment.day >= start)
    if end:
        stmt = stmt.where(SymbolSentiment.day <= end)

    result = await session.execute(stmt.order_by(SymbolSentiment.day))
    rows = result.scalars().all()
    return [
        {
            "symbol": r.symbol,
            "day": r.day.isoformat(),
            "score": r.score,
            "source": r.source,
        }
        for r in rows
    ]
```

Run API:

```bash
uv run --directory backend uvicorn app.main:app --reload
```

Test:

```bash
curl "http://localhost:8000/api/yahoo-apis/sentiment/INFY.NS?start=2026-03-01&end=2026-03-31"
```

---

## 5) Build pipeline script to write data

Create script in `backend/scripts/`.

Pattern:

1. Parse args/env
2. Fetch data from source
3. Open DB session
4. Delete/replace window (idempotent strategy)
5. Insert rows
6. Commit + print count

Example:

```python
# backend/scripts/sync_symbol_sentiment.py
from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta
from random import random

from sqlalchemy import delete

from app.core.config import get_settings
from app.core.db import get_session_factory, close_db
from app.models.symbol_sentiment import SymbolSentiment


def fake_score() -> float:
    return round((2 * random()) - 1, 3)  # -1 to 1


async def upsert_window(session, symbol: str, start: date, end: date) -> int:
    await session.execute(
        delete(SymbolSentiment).where(
            SymbolSentiment.symbol == symbol,
            SymbolSentiment.day >= start,
            SymbolSentiment.day <= end,
        )
    )

    day = start
    inserted = 0
    while day <= end:
        session.add(
            SymbolSentiment(
                symbol=symbol,
                day=day,
                score=fake_score(),
                source="demo",
            )
        )
        inserted += 1
        day += timedelta(days=1)

    await session.commit()
    return inserted


async def main(symbols: list[str], days: int) -> None:
    get_settings()
    end = date.today()
    start = end - timedelta(days=max(0, days - 1))

    factory = get_session_factory()
    async with factory() as session:
        for symbol in symbols:
            n = await upsert_window(session, symbol, start, end)
            print(f"{symbol}: inserted {n} rows ({start}..{end})")

    await close_db()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("symbols", nargs="+")
    p.add_argument("--days", type=int, default=7)
    a = p.parse_args()
    asyncio.run(main(a.symbols, a.days))
```

Run:

```bash
uv run --directory backend python scripts/sync_symbol_sentiment.py INFY.NS TCS.NS --days 7
```

Re-test API route to confirm data flow works.

---

## 6) Add Airflow DAG (optional scheduling)

Once script works manually, schedule it.

Create DAG in `airflow/dags/symbol_sentiment_sync.py`:

```python
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_sentiment_sync(**context):
    root = _repo_root()
    backend = root / "backend"
    script = backend / "scripts" / "sync_symbol_sentiment.py"
    cmd = [
        "uv", "run", "--directory", str(backend),
        "python", str(script), "INFY.NS", "TCS.NS", "--days", "7"
    ]
    r = subprocess.run(cmd, cwd=str(root))
    if r.returncode != 0:
        raise RuntimeError(f"sync failed with exit code {r.returncode}")


with DAG(
    dag_id="medha_symbol_sentiment_sync",
    start_date=datetime(2024, 1, 1),
    schedule="0 7 * * *",
    catchup=False,
    tags=["medha", "sentiment", "etl"],
) as dag:
    sync = PythonOperator(
        task_id="sync_symbol_sentiment",
        python_callable=run_sentiment_sync,
    )
```

Run Airflow test:

```bash
cd airflow
export AIRFLOW_HOME="$(pwd)/airflow_home"
uv run airflow dags test medha_symbol_sentiment_sync 2024-01-01
```

---

## 7) How to think like an engineer (without AI)

Use this build sequence every time:

1. **Define data contract** (fields + types + uniqueness).
2. **Design idempotency** before coding:
   - Replace by date window?
   - Upsert by natural key?
3. **Model + migration first**.
4. **Write pipeline script next** (data write path).
5. **Write read API route last**.
6. **Manual test first, schedule later**.

This avoids building endpoints over tables that are not stable yet.

---

## 8) Common mistakes and fixes

### 1) API works but DB table missing

- Migration not applied on that DB.
- Run:

```bash
uv run --directory backend alembic upgrade head
```

### 2) Pipeline runs but API returns empty

- Pipeline wrote into different DB URL than API is reading.
- Compare `DATABASE_URL` used by both environments.

### 3) Airflow task fails but script works manually

- Environment mismatch inside Airflow worker.
- Prefer subprocess pattern (`uv run --directory backend ...`) and explicit paths.

### 4) Duplicate rows on rerun

- Missing idempotent logic.
- Use `delete window -> insert`, or unique constraint + upsert.

---

## 9) Reusable build checklist (copy/paste)

```bash
# Infra
docker compose up -d postgres
cp backend/.env.example backend/.env
uv sync

# DB
uv run --directory backend alembic revision -m "add <feature> table"
# edit migration file
uv run --directory backend alembic upgrade head

# API
uv run --directory backend uvicorn app.main:app --reload

# Pipeline
uv run --directory backend python scripts/sync_<feature>.py ...

# Airflow (optional)
cd airflow
export AIRFLOW_HOME="$(pwd)/airflow_home"
uv run airflow dags test <your_dag_id> 2024-01-01
```

---

## Final advice

When building alone, do not start with Airflow or UI.
Always do this order:

**DB migration -> script write path -> API read path -> scheduler**

If each layer works before the next one, you can debug quickly and ship confidently.

