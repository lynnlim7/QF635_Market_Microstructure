import msgspec
from app.common.constants import OrderSide

class CreateOrderPayload(msgspec.Struct) : 
    side: OrderSide