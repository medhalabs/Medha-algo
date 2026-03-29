from pydantic import BaseModel


class PlaceForeverBody(BaseModel):
    security_id: str
    exchange_segment: str
    transaction_type: str
    product_type: str
    order_type: str
    quantity: int
    price: float
    trigger_price: float
    order_flag: str = "SINGLE"
    disclosed_quantity: int = 0
    validity: str = "DAY"
    price1: float = 0
    trigger_price1: float = 0
    quantity1: int = 0
    tag: str | None = None
    symbol: str = ""


class ModifyForeverBody(BaseModel):
    order_flag: str
    order_type: str
    leg_name: str
    quantity: int
    price: float
    trigger_price: float
    disclosed_quantity: int
    validity: str
