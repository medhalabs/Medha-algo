from pydantic import BaseModel


class ConvertPositionBody(BaseModel):
    from_product_type: str
    exchange_segment: str
    position_type: str
    security_id: str
    convert_qty: int
    to_product_type: str
