from fastapi import APIRouter, Depends

from app.dhan_api.data.schemas.quotes import SecuritiesMap
from app.deps import get_dhan
from dhanhq import dhanhq

router = APIRouter()


@router.post("/quotes/ticker", summary="Ticker / LTP snapshot")
def ticker_data(body: SecuritiesMap, d: dhanhq = Depends(get_dhan)):
    return d.ticker_data(body.securities)


@router.post("/quotes/ohlc", summary="OHLC snapshot")
def ohlc_data(body: SecuritiesMap, d: dhanhq = Depends(get_dhan)):
    return d.ohlc_data(body.securities)


@router.post("/quotes/full", summary="Full quote snapshot")
def quote_data(body: SecuritiesMap, d: dhanhq = Depends(get_dhan)):
    return d.quote_data(body.securities)
