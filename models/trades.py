from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, Boolean, Enum, DateTime, Numeric, func, ForeignKey
from models import Base
from sqlalchemy.dialects import postgresql
import os

import enum

__all__ = [
    "FuturesOrders",
    "SpotOrders",
]

DEFAULT_SCHEMA = "trading_app"
schema = os.environ.get("APP_SCHEMA", DEFAULT_SCHEMA)

class OrderStatus(enum.Enum):
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


class OrderType(enum.Enum):
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
    # Futures
    STOP = "STOP"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TRAILING_STOP_MARKET = "TRAILING_STOP_MARKET"


class OrderSide(enum.Enum):
    """
    Direction of the order.
    """
    BUY = "BUY"
    SELL = "SELL"

class OrderTimeInForce(enum.Enum) :
    """
    Order time-in-force options:

    - GTC: Good Til Canceled
    - IOC: Immediate Or Cancel
    - FOK: Fill or Kill
    """
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    # Futures
    GTX = "GTX"
    GTD = "GTD"

class OrdersMixin :
    __abstract__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    pair_id = Column(Integer, ForeignKey("futures_pairs.id"), nullable=False)
    filled = Column(Numeric(precision=38, scale=10), nullable=False)
    submitted_at = Column(DateTime(timezone=False), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=False, default=func.now())
    limit_price = Column(Numeric(precision=38, scale=10))
    filled_price = Column(Numeric(precision=38, scale=10), nullable=False)
    amount = Column(Numeric(precision=38, scale=10), nullable=False)
    side = Column(postgresql.ENUM(OrderSide, name="orderside", native_enum=True, create_type=False, schema=schema), nullable=False)
    time_in_force = Column(postgresql.ENUM(OrderTimeInForce, name="ordertimeinforce", native_enum=True, create_type=False, schema=schema))
    status = Column(postgresql.ENUM(OrderStatus, name="orderstatus", schema=schema, create_type=False), nullable=False)
    type = Column(postgresql.ENUM(OrderType, name="ordertype", native_enum=True, create_type=False, schema=schema))
    closed_time = Column(DateTime)
    expired_at = Column(DateTime)

class FuturesOrders(Base, OrdersMixin) : 
    __tablename__= "futures_orders"

    leverage = Column(Integer, nullable=False)


# class FuturesTrades(Base) : 
#     __tablename__ = "futures_trades"
#     id = Column(Integer, primary_key=True)
#     trade_id = Column(Integer, ForeignKey("futures_orders.id"), nullable=False)
#     submit_time = Column(DateTime, nullable=False)
#     closed_time = Column(DateTime, nullable=False)
#     amount = Column(Numeric(precision=38, scale=18), nullable=False)
#     filled_price = Column(Numeric(precision=38, scale=18), nullable=False)
#     type = Column(Enum(OrderType))

class SpotOrders(Base, OrdersMixin) : 
    __tablename__= "spot_orders"
