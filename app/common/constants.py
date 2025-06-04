from enum import Enum

class REDIS_DB_NUM(Enum) :
    SPOT = 0
    FUTURES = 1

class TimeInterval(Enum):
    S1 = "1s"

    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"

    H1 = "1h"
    H2 = "2h"
    H4 = "4h"
    H6 = "6h"
    H8 = "8h"
    H12 = "12h"

    D1 = "1d"
    D3 = "3d"

    W1 = "1w"

    def __str__(self):
        return self.value
    
class OrderStatus(Enum):
    """
    Status of an order in its lifecycle.

    - OPEN: Order is open and waiting to be filled.
    - PENDING: Order is submitted but not yet acknowledged by the exchange.
    - PARTIALLY_FILLED: Order has been partially filled.
    - FILLED: Order has been fully filled.
    - REJECTED: Order was rejected and will not be executed.
    - EXPIRED: Order was not filled within its time-in-force and expired.
    """
    OPEN = "open"
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderType(Enum):
    """
    Type of order execution logic.

    - LIMIT: Executes at a specific price or better.
    - MARKET: Executes immediately at the best available price.
    - STOP_LOSS: Triggers a market order once a stop price is reached.
    - STOP_LIMIT: Triggers a limit order once a stop price is reached.
    - TAKE_PROFIT: Triggers a market order when a target profit price is reached.
    - TAKE_PROFIT_LIMIT: Triggers a limit order when a target profit price is reached.
    - LIMIT_MAKER: A limit order that will only post to the order book (maker only).
    - OCO: One Cancels the Other — a pair of linked orders where the execution of one cancels the other.
    """
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LIMIT = "STOP_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    LIMIT_MAKER = "LIMIT_MAKER"
    OCO = "OCO"


class OrderSide(Enum):
    """
    Direction of the order.
    """
    BUY = "BUY"
    SELL = "SELL"