import asyncio
import queue
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import close_db, get_db_session, init_db
from app.dhan_api.data.router import data_router
from app.dhan_api.trading.router import trading_router
from app.dhan_api.ws import market_feed, order_updates
from app.dhan_api.ws.order_updates import order_broadcast_loop, start_order_thread
from app.yahoo_apis.router import yahoo_apis_router
from dhanhq import dhanhq


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.dhan = dhanhq(settings.dhan_client_id, settings.dhan_access_token)
    app.state.order_queue = queue.Queue()
    app.state.order_update_clients = set()
    start_order_thread(app)
    asyncio.create_task(order_broadcast_loop(app))
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="Medha Dhan API",
    description="FastAPI backend: DhanHQ-py (trading, data, WebSockets) and Yahoo Finance (yfinance).",
    version="0.1.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trading_router, prefix="/api/trading")
app.include_router(data_router, prefix="/api/data")
app.include_router(yahoo_apis_router, prefix="/api/yahoo-apis")
app.include_router(market_feed.router, prefix="/ws")
app.include_router(order_updates.router, prefix="/ws")


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    """Liveness probe (no external dependencies)."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
async def health_ready() -> dict[str, str]:
    """Readiness: verifies Postgres connectivity."""
    try:
        async for session in get_db_session():
            await session.execute(text("SELECT 1"))
            return {"status": "ok", "database": "connected"}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise HTTPException(status_code=503, detail="database session unavailable")
