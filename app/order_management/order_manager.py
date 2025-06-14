from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, Session

from app.api.binance_api import BinanceApi
from models import FuturesOrders, OrderSide, OrderStatus, ExecutionType, OrderType, OrderTimeInForce
from app.utils.logger import main_logger as logger
from app.utils.config import settings


class OrderManager:
    def __init__(self, binance_api: BinanceApi):
        self._binance_api = binance_api
        pg_url = f"postgresql://{settings.APP_PG_USER}:{settings.APP_PG_PASSWORD}@{settings.APP_PG_HOST}:{settings.APP_PG_PORT}/{settings.APP_PG_DB}"
        self._engine = create_engine(pg_url)
        self._session_factory = sessionmaker(bind=self._engine)

    def save_execution_updates(self, order_updates: dict):
        order = self.parse_order(order_updates)
        logger.info(f"Received order_updates from redis: {order.order_id}, order status: {order.status}")

        session: Session = self._session_factory()
        try:
            if order.status == OrderStatus.NEW:
                session.add(order)
                logger.info(f"Inserted new order {order.order_id}")
            else:
                existing = session.get(FuturesOrders, order.order_id)
                if existing:
                    for field, value in order_updates.items():
                        if hasattr(existing, field):
                            setattr(existing, field, value)
                    logger.info(f"Updated existing order {order.order_id}")
                else:
                    logger.warning(f"Order {order.order_id} not found in DB for update")
            session.commit()
        except SQLAlchemyError as e:
            logger.error(f"Database error while saving order {order.order_id}: {e}")
            session.rollback()
        finally:
            session.close()


    def parse_order(self, data: dict) -> FuturesOrders:
        return FuturesOrders(
            order_id=data["order_id"],
            client_order_id=data["client_order_id"],
            symbol=data["symbol"],
            side=OrderSide[data["side"]],
            position_side=data["position_side"],
            exec_type=ExecutionType[data["exec_type"]],
            status=OrderStatus[data["status"]],
            order_type=OrderType[data["order_type"]],
            time_in_force=OrderTimeInForce[data["time_in_force"]],
            orig_qty=data["orig_qty"],
            cum_filled_qty=data["cum_filled_qty"],
            avg_price=data["avg_price"],
            last_qty=data["last_qty"],
            last_price=data["last_price"],
            commission=data["commission"],
            commission_asset=data.get("commission_asset"),
            realized_pnl=data["realized_pnl"],
            stop_price=data["stop_price"],
            activation_price=data["activation_price"],
            callback_rate=data["callback_rate"],
            is_maker=data["is_maker"],
            event_time_ms=data["event_time_ms"],
            trade_time_ms=data["trade_time_ms"]
        )
