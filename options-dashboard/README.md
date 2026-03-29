# Options Dashboard

Uses **Dhan market Data API** endpoints (intraday OHLC, option chain, expiry list). Configure **`DHAN_CLIENT_ID`** and **`DHAN_ACCESS_TOKEN`** from your Dhan developer account with **Data API** access.

```bash
cp .env.example .env
# Edit .env, then:
uv sync
uv run streamlit run app/streamlit_app.py
```

See the repo root `README.md` for the same instructions from the monorepo root.
