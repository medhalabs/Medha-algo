from fastapi import APIRouter, Depends

from app.deps import get_dhan
from app.dhan_api.trading.schemas.portfolio import ConvertPositionBody
from dhanhq import dhanhq

router = APIRouter()


@router.get("/positions", summary="Open positions")
def get_positions(d: dhanhq = Depends(get_dhan)):
    return d.get_positions()


@router.get("/holdings", summary="Holdings")
def get_holdings(d: dhanhq = Depends(get_dhan)):
    return d.get_holdings()


@router.post("/positions/convert", summary="Convert position product type")
def convert_position(body: ConvertPositionBody, d: dhanhq = Depends(get_dhan)):
    return d.convert_position(
        body.from_product_type,
        body.exchange_segment,
        body.position_type,
        body.security_id,
        body.convert_qty,
        body.to_product_type,
    )
