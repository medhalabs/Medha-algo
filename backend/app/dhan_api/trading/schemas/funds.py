from pydantic import BaseModel


class MarginCalculatorBody(BaseModel):
    security_id: str
    exchange_segment: str
    transaction_type: str
    quantity: int
    product_type: str
    price: float
    trigger_price: float = 0
