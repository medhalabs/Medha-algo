from typing import Any

from pydantic import BaseModel


class SecuritiesMap(BaseModel):
    """Maps exchange segment keys to lists of security ids (see Dhan `ticker_data` / `ohlc_data`)."""

    securities: dict[str, list[Any]]


class OptionChainBody(BaseModel):
    under_security_id: int
    under_exchange_segment: str
    expiry: str


class ExpiryListBody(BaseModel):
    under_security_id: int
    under_exchange_segment: str


class IntradayBody(BaseModel):
    security_id: str
    exchange_segment: str
    instrument_type: str
    from_date: str
    to_date: str
    interval: int = 1


class HistoricalDailyBody(BaseModel):
    security_id: str
    exchange_segment: str
    instrument_type: str
    from_date: str
    to_date: str
    expiry_code: int = 0


class EpochBody(BaseModel):
    epoch: int
