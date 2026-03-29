from fastapi import APIRouter, Depends

from app.deps import get_dhan
from app.dhan_api.trading.schemas.orders import (
    ModifyOrderBody,
    PlaceOrderBody,
    SliceOrderBody,
)
from dhanhq import dhanhq

router = APIRouter()


@router.get("", summary="List orders for the day")
def list_orders(d: dhanhq = Depends(get_dhan)):
    return d.get_order_list()


@router.get("/external/{correlation_id}", summary="Get order by correlation id")
def get_order_by_correlation(correlation_id: str, d: dhanhq = Depends(get_dhan)):
    return d.get_order_by_correlationID(correlation_id)


@router.get("/{order_id}", summary="Get order by id")
def get_order(order_id: str, d: dhanhq = Depends(get_dhan)):
    return d.get_order_by_id(order_id)


@router.post("", summary="Place order")
def place_order(body: PlaceOrderBody, d: dhanhq = Depends(get_dhan)):
    return d.place_order(
        security_id=body.security_id,
        exchange_segment=body.exchange_segment,
        transaction_type=body.transaction_type,
        quantity=body.quantity,
        order_type=body.order_type,
        product_type=body.product_type,
        price=body.price,
        trigger_price=body.trigger_price,
        disclosed_quantity=body.disclosed_quantity,
        after_market_order=body.after_market_order,
        validity=body.validity,
        amo_time=body.amo_time,
        bo_profit_value=body.bo_profit_value,
        bo_stop_loss_Value=body.bo_stop_loss_value,
        tag=body.tag,
    )


@router.post("/slice", summary="Place slice order")
def place_slice_order(body: SliceOrderBody, d: dhanhq = Depends(get_dhan)):
    return d.place_slice_order(
        security_id=body.security_id,
        exchange_segment=body.exchange_segment,
        transaction_type=body.transaction_type,
        quantity=body.quantity,
        order_type=body.order_type,
        product_type=body.product_type,
        price=body.price,
        trigger_price=body.trigger_price,
        disclosed_quantity=body.disclosed_quantity,
        after_market_order=body.after_market_order,
        validity=body.validity,
        amo_time=body.amo_time,
        bo_profit_value=body.bo_profit_value,
        bo_stop_loss_Value=body.bo_stop_loss_value,
        tag=body.tag,
    )


@router.put("/{order_id}", summary="Modify pending order")
def modify_order(
    order_id: str,
    body: ModifyOrderBody,
    d: dhanhq = Depends(get_dhan),
):
    return d.modify_order(
        order_id,
        body.order_type,
        body.leg_name,
        body.quantity,
        body.price,
        body.trigger_price,
        body.disclosed_quantity,
        body.validity,
    )


@router.delete("/{order_id}", summary="Cancel order")
def cancel_order(order_id: str, d: dhanhq = Depends(get_dhan)):
    return d.cancel_order(order_id)
