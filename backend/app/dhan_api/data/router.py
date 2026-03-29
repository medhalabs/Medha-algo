from fastapi import APIRouter

from app.dhan_api.data.routes import chain, historical, quotes, securities

data_router = APIRouter()
data_router.include_router(quotes.router, tags=["Data"])
data_router.include_router(historical.router, tags=["Data"])
data_router.include_router(chain.router, tags=["Data"])
data_router.include_router(securities.router, tags=["Data"])
