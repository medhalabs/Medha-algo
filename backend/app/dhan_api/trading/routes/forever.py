from fastapi import APIRouter, Depends

from app.deps import get_dhan
from app.dhan_api.trading.schemas.forever import ModifyForeverBody, PlaceForeverBody
from dhanhq import dhanhq

router = APIRouter()


@router.get("/forever/orders", summary="List forever orders")
def list_forever(d: dhanhq = Depends(get_dhan)):
    return d.get_forever()


@router.post("/forever/orders", summary="Place forever order")
def place_forever(body: PlaceForeverBody, d: dhanhq = Depends(get_dhan)):
    return d.place_forever(
        security_id=body.security_id,
        exchange_segment=body.exchange_segment,
        transaction_type=body.transaction_type,
        product_type=body.product_type,
        order_type=body.order_type,
        quantity=body.quantity,
        price=body.price,
        trigger_Price=body.trigger_price,
        order_flag=body.order_flag,
        disclosed_quantity=body.disclosed_quantity,
        validity=body.validity,
        price1=body.price1,
        trigger_Price1=body.trigger_price1,
        quantity1=body.quantity1,
        tag=body.tag,
        symbol=body.symbol,
    )


@router.put("/forever/orders/{order_id}", summary="Modify forever order")
def modify_forever(
    order_id: str,
    body: ModifyForeverBody,
    d: dhanhq = Depends(get_dhan),
):
    return d.modify_forever(
        order_id,
        body.order_flag,
        body.order_type,
        body.leg_name,
        body.quantity,
        body.price,
        body.trigger_price,
        body.disclosed_quantity,
        body.validity,
    )


@router.delete("/forever/orders/{order_id}", summary="Cancel forever order")
def cancel_forever(order_id: str, d: dhanhq = Depends(get_dhan)):
    return d.cancel_forever(order_id)
