from fastapi import APIRouter, Depends, Query

from app.deps import get_dhan
from app.dhan_api.trading.schemas.orders import KillSwitchBody
from dhanhq import dhanhq

router = APIRouter()


@router.get("/tpin/generate", summary="Generate T-PIN (OTP to mobile)")
def generate_tpin(d: dhanhq = Depends(get_dhan)):
    return d.generate_tpin()


@router.get("/edis/inquiry/{isin}", summary="eDIS inquiry for ISIN")
def edis_inquiry(isin: str, d: dhanhq = Depends(get_dhan)):
    return d.edis_inquiry(isin)


@router.post("/kill-switch", summary="Activate or deactivate kill switch")
def kill_switch(body: KillSwitchBody, d: dhanhq = Depends(get_dhan)):
    return d.kill_switch(body.action)


@router.get("/tpin/form", summary="Fetch eDIS form HTML (browser flow)")
def open_tpin_form(
    isin: str = Query(...),
    qty: int = Query(...),
    exchange: str = Query(...),
    segment: str = Query("EQ"),
    bulk: bool = Query(False),
    d: dhanhq = Depends(get_dhan),
):
    return d.open_browser_for_tpin(isin=isin, qty=qty, exchange=exchange, segment=segment, bulk=bulk)
