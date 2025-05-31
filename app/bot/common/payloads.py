import msgspec
from bot.common.constants import OrderSide

class CreateOrderPayload(msgspec.Struct) : 
    side: OrderSide