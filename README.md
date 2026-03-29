# Medha Options Dashboard

## Run

From the repo root:

```bash
uv sync
cp options-dashboard/.env.example options-dashboard/.env
# Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN in options-dashboard/.env
uv run --directory options-dashboard streamlit run app/streamlit_app.py
```

From `options-dashboard/`:

```bash
cd options-dashboard
uv sync
cp .env.example .env
uv run streamlit run app/streamlit_app.py
```
