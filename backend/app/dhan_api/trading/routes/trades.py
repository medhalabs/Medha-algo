from fastapi import APIRouter, Depends, Query

from app.deps import get_dhan
from dhanhq import dhanhq

router = APIRouter()


@router.get("/tradebook", summary="Trade book (optional filter by order id)")
def trade_book(
    order_id: str | None = Query(None),
    d: dhanhq = Depends(get_dhan),
):
    return d.get_trade_book(order_id)


@router.get("/trade-history", summary="Trade history by date range")
def trade_history(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    page_number: int = Query(0, ge=0),
    d: dhanhq = Depends(get_dhan),
):
    return d.get_trade_history(from_date, to_date, page_number)


@router.get("/ledger", summary="Ledger report")
def ledger_report(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    d: dhanhq = Depends(get_dhan),
):
    return d.ledger_report(from_date, to_date)
