import msgspec
from models.json import TimeInterval
from decimal import Decimal

# Average Price (avgPrice)
class AveragePrice(msgspec.Struct) : 
    event : str = msgspec.field(name="e")
    event_time : str = msgspec.field(name="E")
    symbol : str = msgspec.field(name="s")
    interval : TimeInterval = msgspec.field(name="i")
    price : Decimal = msgspec.field(name="w")
    last_trade : str = msgspec.field(name="T")
    
    @property
    def price(self) : 
        return Decimal(self.w)
    

# Best bid-ask (bookTicker)
class BookTicker(msgspec.Struct) : 
    update_id : int = msgspec.field(name="u")
    symbol : str = msgspec.field(name="s")
    b : str
    B : str
    a : str
    A : str

    @property
    def best_bid(self) : 
        return Decimal(self.b)
    
    @property
    def best_bid_qty(self) :
        return Decimal(self.B)
    
    @property
    def best_ask(self) : 
        return Decimal(self.a)
    
    @property
    def best_ask_qty(self) :
        return Decimal(self.A)

    @property
    def weighted_price(self) :
        numerator = self.best_ask * self.best_ask_qty + self.best_bid * self.best_bid_qty
        denominator = self.best_ask_qty + self.best_bid_qty
        return numerator/denominator
    
