from fastapi import APIRouter, Depends

from app.dhan_api.data.schemas.quotes import HistoricalDailyBody, IntradayBody
from app.deps import get_dhan
from dhanhq import dhanhq

router = APIRouter()


@router.post("/historical/intraday", summary="Intraday minute OHLC")
def intraday_minute(body: IntradayBody, d: dhanhq = Depends(get_dhan)):
    return d.intraday_minute_data(
        body.security_id,
        body.exchange_segment,
        body.instrument_type,
        body.from_date,
        body.to_date,
        body.interval,
    )


@router.post("/historical/daily", summary="Daily OHLC history")
def historical_daily(body: HistoricalDailyBody, d: dhanhq = Depends(get_dhan)):
    return d.historical_daily_data(
        body.security_id,
        body.exchange_segment,
        body.instrument_type,
        body.from_date,
        body.to_date,
        body.expiry_code,
    )
