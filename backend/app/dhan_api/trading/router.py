from fastapi import APIRouter

from app.dhan_api.trading.routes import edis, forever, funds, orders, portfolio, trades

trading_router = APIRouter()
trading_router.include_router(orders.router, prefix="/orders", tags=["Trading"])
trading_router.include_router(portfolio.router, tags=["Trading"])
trading_router.include_router(funds.router, tags=["Trading"])
trading_router.include_router(forever.router, tags=["Trading"])
trading_router.include_router(trades.router, tags=["Trading"])
trading_router.include_router(edis.router, tags=["Trading"])
