import io
from typing import Any

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, Query

from app.deps import get_dhan
from app.dhan_api.data.schemas.quotes import EpochBody
from dhanhq import dhanhq

router = APIRouter()

COMPACT_CSV_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
DETAILED_CSV_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"


@router.get("/securities/csv", summary="Download instrument master as JSON rows (no local file)")
async def fetch_security_list_json(
    mode: str = Query("compact", pattern="^(compact|detailed)$"),
    limit: int | None = Query(None, ge=1, le=500_000, description="Max rows to return"),
) -> dict[str, Any]:
    url = COMPACT_CSV_URL if mode == "compact" else DETAILED_CSV_URL
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(url)
        r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content))
    if limit is not None:
        df = df.head(limit)
    return {"mode": mode, "rows": int(len(df)), "data": df.to_dict(orient="records")}


@router.post("/time/epoch-to-ist", summary="Convert epoch to IST datetime string (SDK helper)")
def convert_epoch(body: EpochBody, d: dhanhq = Depends(get_dhan)):
    dt = d.convert_to_date_time(body.epoch)
    return {"datetime_ist": str(dt)}
