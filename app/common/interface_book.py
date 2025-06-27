from typing import List, Optional
import msgspec
from decimal import Decimal
# A price tier in the order book

class PriceLevel(msgspec.Struct, gc=False, array_like=True):
    price : Decimal
    size : Decimal

    def __str__(self):
        return '[' + str(self.price) + " | " + str(self.size) + ']'

# An order book with bid and ask sides
class OrderBook(msgspec.Struct, frozen=True) :
    contract_name : str
    timestamp : int 
    bids : List[PriceLevel]
    asks : List[PriceLevel]

    def __str__(self):
        string = ' BIDS: '
        for tier in self.bids[:5]:
            string += str(tier)

        string = string + ' ASK: '
        for tier in self.asks[:5]:
            string += str(tier)

        return string

    def get_best_bid(self):
        if len(self.bids) > 0 :
            return self.bids[0].price
        return 0

    def get_best_ask(self):
        if len(self.asks) > 0 : 
            return self.asks[0].price
        return 0

# A venue order book telling us the exchange that provides the order book
class VenueOrderBook:
    def __init__(self, exchange_name: str, book: OrderBook):
        self.exchange_name = exchange_name
        self.book = book

    def get_book(self):
        return self.book

    def __str__(self):
        return '{}={}'.format(self.exchange_name, self.book)
    
class KlineEvent(msgspec.Struct, array_like=True, gc=False) :
    symbol: str
    interval: str
    open: float
    close: float
    high: float
    low: float
    volume: float
    is_closed: bool
    start_time: int
    end_time: int
    source: str = "candlestick"  # optional with default value

    @classmethod
    def from_dict(cls, data: dict) -> "KlineEvent":
        return cls(**data)