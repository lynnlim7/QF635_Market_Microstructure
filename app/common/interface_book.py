# A price tier in the order book
class PriceLevel:
    def __init__(self, price: float, size: float, quote_id: str = None):
        self.price = price
        self.size = size
        self.quote_id = quote_id

    def __str__(self):
        return '[' + str(self.price) + " | " + str(self.size) + ']'

    def to_dict(self):
        return {"price": self.price, "quantity": self.size, "quote_id": self.quote_id}

# An order book with bid and ask sides
class OrderBook:
    def __init__(self, timestamp: float, contract_name: str, bids: [PriceLevel], asks: [PriceLevel]):
        self.contract_name = contract_name
        self.timestamp = timestamp
        self.bids = bids
        self.asks = asks

    def __str__(self):
        string = ' BIDS: '
        for tier in self.bids[:5]:
            string += str(tier)

        string = string + ' ASK: '
        for tier in self.asks[:5]:
            string += str(tier)

        return string

    def get_best_bid(self):
        return self.bids[0].price

    def get_best_ask(self):
        return self.asks[0].price

    def to_dict(self):
        return {
            "contract_name": self.contract_name,
            "timestamp": self.timestamp,
            "bids": [b.to_dict() for b in self.bids],
            "asks": [a.to_dict() for a in self.asks],
        }

# A venue order book telling us the exchange that provides the order book
class VenueOrderBook:
    def __init__(self, exchange_name: str, book: OrderBook):
        self.exchange_name = exchange_name
        self.book = book

    def get_book(self):
        return self.book

    def __str__(self):
        return '{}={}'.format(self.exchange_name, self.book)