import enum
import os

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Numeric,
    String,
)
from sqlalchemy.dialects import postgresql

from models import Base

__all__ = [
    "FuturesOrders",
    "OrderStatus",
    "OrderType",
    "OrderSide",
    "OrderTimeInForce",
    "ExecutionType"
]

DEFAULT_SCHEMA = "trading_app"
schema = os.environ.get("APP_SCHEMA", DEFAULT_SCHEMA)

class ExecutionType(enum.Enum):
    """
    Status of an order in its lifecycle.

    - Refer to for complete list of values: https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Order-Update
    """
    NEW = "NEW"
    CANCELED = "CANCELED"
    CALCULATED = "CALCULATED"
    TRADE = "TRADE"
    EXPIRED = "EXPIRED"
    AMENDMENT = "AMENDMENT"



class OrderStatus(enum.Enum):
    """
    Status of an order in its lifecycle.

    - Refer to for complete list of values: https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Order-Update
    """
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    EXPIRED_IN_MATCH = "EXPIRED_IN_MATCH" #not sure whats this


class OrderType(enum.Enum):
    """
    Type of order execution logic.

    - Refer to for complete list of values: https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Order-Update
    """
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    TAKE_PROFIT = "TAKE_PROFIT"
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

    # primary key – Binance order id is unique per account
    order_id = Column(BigInteger, primary_key=True)

    # identifiers & symbol
    client_order_id = Column(String(64), nullable=False)
    symbol          = Column(String(16), nullable=False)        # e.g. BTCUSDT

    # lifecycle enums
    side            = Column(
        postgresql.ENUM(OrderSide, name="orderside", schema=schema, native_enum=True, create_type=False),
        nullable=False,
    )
    position_side   = Column(String(8), nullable=False)         # LONG / SHORT / BOTH
    exec_type       = Column(
        postgresql.ENUM(ExecutionType, name="executiontype", schema=schema, create_type=False),
        nullable=False,
    )
    status          = Column(
        postgresql.ENUM(OrderStatus, name="orderstatus", schema=schema, create_type=False),
        nullable=False,
    )
    order_type      = Column(
        postgresql.ENUM(OrderType, name="ordertype", schema=schema, create_type=False),
        nullable=False,
    )
    time_in_force   = Column(
        postgresql.ENUM(OrderTimeInForce, name="ordertimeinforce", schema=schema, create_type=False),
        nullable=True,
    )

    # quantities / prices ----------------------------------------------------
    orig_qty       = Column(Numeric(38, 10), nullable=False)
    cum_filled_qty = Column(Numeric(38, 10), nullable=False)
    avg_price      = Column(Numeric(38, 10))
    last_qty       = Column(Numeric(38, 10), nullable=False)
    last_price     = Column(Numeric(38, 10))
    commission     = Column(Numeric(38, 10), nullable=False)
    commission_asset = Column(String(12))
    realized_pnl     = Column(Numeric(38, 10), nullable=False)

    # trailing / stop fields -------------------------------------------------
    stop_price       = Column(Numeric(38, 10))
    activation_price = Column(Numeric(38, 10))
    callback_rate    = Column(Numeric(38, 10))

    # misc flags & raw timestamps -------------------------------------------
    is_maker      = Column(Boolean, nullable=False, default=False)
    event_time_ms = Column(BigInteger, nullable=False)
    trade_time_ms = Column(BigInteger, nullable=False)

class FuturesOrders(Base, OrdersMixin) : 
    __tablename__= "futures_order"

