from fastapi import APIRouter

from app.yahoo_apis.routes import calendar, download, search, ticker

yahoo_apis_router = APIRouter()
yahoo_apis_router.include_router(ticker.router, prefix="/ticker", tags=["Yahoo APIs"])
yahoo_apis_router.include_router(download.router, tags=["Yahoo APIs"])
yahoo_apis_router.include_router(search.router, prefix="/search", tags=["Yahoo APIs"])
yahoo_apis_router.include_router(calendar.router, prefix="/calendar", tags=["Yahoo APIs"])
