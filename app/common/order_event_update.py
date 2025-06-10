from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict

from app.utils.data_class_utils import to_clean_dict
from models import OrderStatus, ExecutionType
from models.trades import OrderType, OrderSide, OrderTimeInForce

SGT = timezone(timedelta(hours=8))  # Singapore Time

# frozen means you cant edit the variables, remove if deemed necessary
@dataclass(slots=True, frozen=True)
class OrderEventUpdate:
    # ---- core identifiers ---------------------------------------------------
    symbol: str
    order_id: int
    client_order_id: str
    side: OrderSide
    position_side: str           # LONG / SHORT / BOTH

    # ---- order life-cycle & exec info ---------------------------------------
    exec_type: ExecutionType               # NEW / TRADE / CANCELED / …
    status: OrderStatus
    order_type: OrderType
    time_in_force: OrderTimeInForce           # GTC / IOC / FOK / GTD

    # ---- quantities & prices (running totals) ------------------------------
    orig_qty: Decimal
    cum_filled_qty: Decimal
    avg_price: Decimal

    # ---- last execution “delta” --------------------------------------------
    last_qty: Decimal
    last_price: Decimal
    commission: Decimal

    realized_pnl: Decimal
    is_maker: bool

    # ---- timestamps ---------------------------------------------------------
    event_time_ms: int
    trade_time_ms: int

    # ---- misc (stop-loss / trailing-stop etc.) ------------------------------
    stop_price: Decimal
    activation_price: Decimal
    callback_rate: Decimal

    # ------------------------------------------------------------------------
    @classmethod
    def from_user_stream(cls, raw: Dict[str, Any]) -> "OrderEventUpdate":
        """Factory: parse the `ORDER_TRADE_UPDATE` payload coming from Binance user-data stream."""
        if raw.get("e") != "ORDER_TRADE_UPDATE":
            raise ValueError("Not an ORDER_TRADE_UPDATE message")

        o = raw["o"]

        d = cls(
            symbol=o["s"],
            order_id=o["i"],
            client_order_id=o["c"],
            side=o["S"],
            position_side=o["ps"],

            exec_type=o["x"],
            status=o["X"],
            order_type=o["o"],
            time_in_force=o["f"],

            orig_qty=Decimal(o["q"]),
            cum_filled_qty=Decimal(o["z"]),
            avg_price=Decimal(o["ap"]),

            last_qty=Decimal(o["l"]),
            last_price=Decimal(o["L"]),
            commission=Decimal(o["n"]),

            realized_pnl=Decimal(o["rp"]),
            is_maker=o["m"],

            event_time_ms=raw["E"],
            trade_time_ms=o["T"],

            stop_price=Decimal(o["sp"]),
            activation_price=Decimal(o.get("AP", "0")),
            callback_rate=Decimal(o.get("cr", "0")),
        )
        return d

    def to_dict(self):
        return to_clean_dict(self)

# ---------- helper -----------------------------------------------------------
def _millis_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp=ms / 1_000.0, tz=SGT)
