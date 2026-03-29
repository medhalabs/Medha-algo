from pydantic import BaseModel, Field


class PlaceOrderBody(BaseModel):
    security_id: str
    exchange_segment: str
    transaction_type: str
    quantity: int
    order_type: str
    product_type: str
    price: float = 0
    trigger_price: float = 0
    disclosed_quantity: int = 0
    after_market_order: bool = False
    validity: str = "DAY"
    amo_time: str = "OPEN"
    bo_profit_value: float | None = None
    bo_stop_loss_value: float | None = Field(None, alias="bo_stop_loss_Value")
    tag: str | None = None

    model_config = {"populate_by_name": True}


class SliceOrderBody(PlaceOrderBody):
    pass


class ModifyOrderBody(BaseModel):
    order_type: str
    leg_name: str
    quantity: int
    price: float
    trigger_price: float
    disclosed_quantity: int
    validity: str


class KillSwitchBody(BaseModel):
    action: str  # activate | deactivate (SDK uppercases)
