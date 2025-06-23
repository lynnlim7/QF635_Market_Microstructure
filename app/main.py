# from binance import SIDE_BUY, ORDER_TYPE_LIMIT, TIME_IN_FORCE_GTC
import threading
import time

from flask import Flask

from app.analytics.TradeAnalysis import TradeAnalysis
from app.api.base_api import BaseApi
from app.api.base_gateway import BaseGateway
from app.api.binance_api import BinanceApi
from app.api.binance_gateway import BinanceGateway
from app.api.mock.mock_binance_api import MockBinanceApi
from app.api.mock.mock_binance_gateway import MockBinanceGateway
from app.order_management.order_manager import OrderManager
from app.portfolio.portfolio_manager import PortfolioManager
from app.queue_manager.locking_queue import LockingQueue
from app.risk.risk_manager import RiskManager
from app.routes import register_routes
from app.services import RedisPool
from app.strategy.base_strategy import BaseStrategy
from app.strategy.macd_strategy import MACDStrategy
from app.queue_manager.locking_queue import LockingQueue
from app.strategy.random_strategy import RandomStrategy
from app.utils.config import settings
from app.utils.func import get_execution_channel, get_orderbook_channel, get_candlestick_channel
from app.utils.logger import main_logger as logger

symbol = settings.SYMBOL

## list of redis channels
redis_channels = [
    get_candlestick_channel(symbol.lower()),
    get_orderbook_channel(symbol.lower()),
    get_execution_channel(symbol.lower())
    # add in other channels 
    ]

gateway_instance: BaseGateway | None = None
strategy_instance: BaseStrategy | None = None

redis_pool = RedisPool()

circuit_breaker = redis_pool.create_circuit_breaker()
publisher = redis_pool.create_publisher()

if settings.IS_SIMULATION:
    binance_api = MockBinanceApi(symbol=settings.SYMBOL, redis_publisher=publisher)
else:
    binance_api = BinanceApi(settings.SYMBOL)

portfolio_manager = PortfolioManager()
risk_manager = RiskManager(
    symbol=symbol,
    api=binance_api,
    portfolio_manager=portfolio_manager,
    circuit_breaker=circuit_breaker
)

order_manager = OrderManager(
    binance_api=binance_api
)



app = Flask(__name__)
register_routes(app, binance_api)

# Create global signal queue_manager
signal_queue = LockingQueue()
order_queue = LockingQueue()

# Global shutdown flag
emergency_shutdown_triggered = False

def emergency_shutdown_callback(reason: str):
    global emergency_shutdown_triggered
    logger.critical(f"Emergency shutdown callback triggered: {reason}")

    if not emergency_shutdown_triggered:
        emergency_shutdown_triggered = True

        # Trigger emergency liquidation in risk manager
        if 'risk_manager' in globals():
            try:
                risk_manager.emergency_liquidation()
            except Exception as e:
                logger.error(f"Error during emergency liquidation: {e}")

        logger.critical("All trading activity stopped and positions liquidated.")

def start_binance() -> None:
    logger.info("Starting binance now")
    global gateway_instance
    if settings.IS_SIMULATION:
        # todo: may need symbol
        gateway_instance = MockBinanceGateway(symbol=symbol, redis_publisher=publisher)
    else:
        gateway_instance = BinanceGateway(symbol=symbol, redis_publisher=publisher)
    gateway_instance.connection()

def handle_order_book_quote(data: dict):
    # logger.info(f"Receiving order book quote from redis!!: {data}")
    # portfolio_manager.on_new_price(data)
    # risk_manager.on_new_orderbook(data)
    pass

def handle_execution_updates(data: dict):
    order_queue.push(data)

def start_subscriber():
    logger.info("Starting subscriber now")
    ## subscribe to redis channel
    subscriber = redis_pool.create_subscriber(redis_channels)
    logger.info(f"Created Redis subscriber for channels: {redis_channels}")

    # register handler for diff modules
    global strategy_instance
    while strategy_instance is None:
        logger.info("Waiting for strategy to start")
        time.sleep(1)
    logger.info("Strategy loaded")

    global order_manager

    for channel in redis_channels:
        logger.info(f"Registering handlers for channel: {channel}")
        if "candlestick" in channel:
            subscriber.register_handler(channel, strategy_instance.update_data)
            subscriber.register_handler(channel, risk_manager.on_new_candlestick)
            logger.info(f"Registered candlestick handlers for {channel}")

        if "execution" in channel:
            subscriber.register_handler(channel, handle_execution_updates)
            subscriber.register_handler(channel, portfolio_manager.on_new_trade)
            logger.info(f"Registered execution handlers for {channel}")

        if "orderbook" in channel:
            subscriber.register_handler(channel, handle_order_book_quote)
            subscriber.register_handler(channel, portfolio_manager.on_new_price)
            subscriber.register_handler(channel, risk_manager.on_new_orderbook)
            if settings.IS_SIMULATION:
                subscriber.register_handler(channel, binance_api.on_new_price)

            logger.info(f"Registered orderbook handlers for {channel}")

    logger.info("Starting Redis subscriber...")
    subscriber.start_subscribing()
    logger.info("Redis subscriber started")

def start_flask():
    # global app
    app.run(host="0.0.0.0", debug=True, use_reloader=False, port=8080)  # disable reloader in threaded mode

# Intermediate callback to push signals into the queue_manager
def signal_callback(signal: int):
    logger.info(f"Signal pushed to queue: {signal}")
    signal_queue.push(signal)

def signal_consumer_loop():
    sleep_time = 0.001 if settings.IS_SIMULATION else 1

    while True:
        if emergency_shutdown_triggered:
            logger.critical("Emergency shutdown: Signal consumer loop stopped.")
            break

        if not signal_queue.is_empty():
            signal = signal_queue.pop()
            if signal is not None:
                # signal is actually a pair value
                risk_manager.on_signal_update(signal[1], symbol)
        time.sleep(sleep_time)


def order_consumer_loop():
    sleep_time = 0.001 if settings.IS_SIMULATION else 1

    while True:
        if emergency_shutdown_triggered:
            logger.critical("Emergency shutdown: Order consumer loop stopped.")
            break

        if not order_queue.is_empty() and order_manager:
            data = order_queue.pop()
            if data[1] is not None:
                order_manager.save_execution_updates(data[1])
        time.sleep(sleep_time)

def background_drawdown_check():
    while True:
        if emergency_shutdown_triggered:
            logger.critical("Emergency shutdown: Background drawdown check stopped")
            break

        try:
            logger.info("Checking drawdown limits...")
            if not risk_manager.drawdown_limit_check(symbol):
                logger.warning("Drawdown limits breached. Opening circuit breaker.")
                circuit_breaker.force_open("Drawdown limits breached.")
                break
            else:
                logger.info("Drawdown limits are within acceptable range.")
        except Exception as e:
            logger.error(f"Error in drawdown check: {e}", exc_info=True)
        time.sleep(30)


def main():
    logger.info(f"Start trading.. is_simulation: {settings.IS_SIMULATION}")

    circuit_breaker = redis_pool.create_circuit_breaker()
    circuit_breaker.set_emergency_callback(emergency_shutdown_callback)
    logger.info("Emergency shutdown callback registered with circuit breaker")

    global strategy_instance

    # strategy_instance = RandomStrategy(symbol)
    strategy_instance = MACDStrategy(symbol)
    strategy_instance.register_callback(signal_callback)
    logger.info("Strategy instance created and callback registered")


    while True:
        if emergency_shutdown_triggered:
            logger.critical("Stopping all trading activity")
            break

        time.sleep(60)


if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    threading.Thread(target=start_binance, daemon=True).start()
    threading.Thread(target=start_subscriber, daemon=True).start()
    threading.Thread(target=signal_consumer_loop, daemon=True).start()
    threading.Thread(target=order_consumer_loop, daemon=True).start()
    # threading.Thread(target=lambda: asyncio.run(run_trade_analysis()), daemon=True).start()
    threading.Thread(target=background_drawdown_check, daemon=True).start()
    main()