from fastapi import APIRouter, Depends

from app.deps import get_dhan
from app.dhan_api.trading.schemas.funds import MarginCalculatorBody
from dhanhq import dhanhq

router = APIRouter()


@router.get("/fund/limits", summary="Fund limits and margin summary")
def fund_limits(d: dhanhq = Depends(get_dhan)):
    return d.get_fund_limits()


@router.post("/margin/calculator", summary="Margin calculator")
def margin_calculator(body: MarginCalculatorBody, d: dhanhq = Depends(get_dhan)):
    return d.margin_calculator(
        body.security_id,
        body.exchange_segment,
        body.transaction_type,
        body.quantity,
        body.product_type,
        body.price,
        body.trigger_price,
    )
