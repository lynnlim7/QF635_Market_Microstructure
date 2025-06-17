# from binance import SIDE_BUY, ORDER_TYPE_LIMIT, TIME_IN_FORCE_GTC
import threading
import time
import asyncio

from flask import Flask

from app.api.binance_api import BinanceApi
from app.api.binance_gateway import BinanceGateway
from app.order_management.order_manager import OrderManager
from app.portfolio.portfolio_manager import PortfolioManager
from app.analytics.TradeAnalysis import run_trade_analysis, get_trade_summary
from app.risk.risk_manager import RiskManager
from app.routes import register_routes
from app.services import RedisPool
from app.services.circuit_breaker import RedisCircuitBreaker
from app.strategy.base_strategy import BaseStrategy
from app.strategy.macd_strategy import MACDStrategy
from app.queue_manager.locking_queue import LockingQueue
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

gateway_instance: BinanceGateway | None = None
strategy_instance: BaseStrategy | None = None
binance_api = BinanceApi(settings.SYMBOL)

redis_pool = RedisPool()
# redis_pool.create_circuit_breaker()

circuit_breaker = redis_pool.create_circuit_breaker()
publisher = redis_pool.create_publisher()
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

def start_binance() -> None:
    logger.info("Starting binance now")
    global gateway_instance
    gateway_instance = BinanceGateway(symbol=symbol, redis_publisher=publisher)
    gateway_instance.connection()

def handle_order_book_quote(data: dict):
    # logger.info(f"Receiving order book quote from redis!!: {data}")
    return

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
            subscriber.register_handler(channel, risk_manager.process_candlestick)
            logger.info(f"Registered candlestick handlers for {channel}")

        if "execution" in channel:
            subscriber.register_handler(channel, handle_execution_updates)
            subscriber.register_handler(channel, portfolio_manager.on_new_trade)
            logger.info(f"Registered execution handlers for {channel}")

        if "orderbook" in channel:
            subscriber.register_handler(channel, handle_order_book_quote)
            subscriber.register_handler(channel, portfolio_manager.on_new_price)
            subscriber.register_handler(channel, risk_manager.process_orderbook)
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
    while True:
        if not signal_queue.is_empty():
            signal = signal_queue.pop()
            if signal is not None:
                risk_manager.accept_signal(signal, symbol)
        time.sleep(1)

def order_consumer_loop():
    while True:
        if not order_queue.is_empty() and order_manager:
            data = order_queue.pop()
            if data[1] is not None:
                order_manager.save_execution_updates(data[1])
        time.sleep(1)

def main():
    logger.info(f"Start trading..")

    ## initialize modules
    circuit_breaker = redis_pool.create_circuit_breaker()
    global strategy_instance
    strategy_instance = MACDStrategy(symbol)
    strategy_instance.register_callback(signal_callback)
    logger.info("Strategy instance created and callback registered")

    while True:
        try: 
            if not circuit_breaker.allow_request():
                logger.warning(f"Circuit breaker is open. Stop trading.")
                time.sleep(5)
                continue

            current_prices = {}
            
            orderbook_data = risk_manager.df_orderbook.get(symbol)
            price_data = risk_manager.df_candlestick.get(symbol)

            if orderbook_data is not None and len(orderbook_data) > 0:
                current_price = orderbook_data['mid_price'].iloc[-1]
                current_prices[symbol] = current_price
                logger.info(f"Current mid price for {symbol}: {current_price:.4f}")

                atr = risk_manager.calculate_atr()
                position_size = risk_manager.calculate_position_size()

                if atr is not None:
                    logger.info(f"Average True Range: {atr:.4f}")
                if position_size is not None:
                    logger.info(f"Position Size: {position_size:.4f}")

                drawdown_limit_check = risk_manager.calculate_drawdown_limits(symbol, current_prices)
                if drawdown_limit_check == False:
                    logger.warning("Drawdown limits breached. Opening circuit breaker.")
                    circuit_breaker.force_open("Drawdown limits breached.")
                    continue

                portfolio_stats = risk_manager.portfolio_manager.get_portfolio_stats_by_symbol(symbol)
                position = portfolio_stats['position']
                
                if position is None or position['qty'] == 0:
                    if not signal_queue.is_empty():
                        signal = signal_queue.pop()
                        if signal is not None:
                            direction = risk_manager.accept_signal(signal, symbol)
                            logger.info(f"Signal {signal} accepted with direction: {direction}")
                            if direction:
                                entry_signal = risk_manager.entry_position(symbol, direction)
                                if entry_signal is not None:
                                    stop_loss, take_profit = entry_signal
                                    logger.info(f"Entry signal received - Stop Loss: {stop_loss:.4f}, Take Profit: {take_profit:.4f}")
                                else:
                                    logger.warning(f"Entry position returned None for direction {direction}")
                            else:
                                logger.info("No valid signal direction received")
                else:
                    logger.info(f"Position already exists for {symbol}, managing position")
                    risk_manager.manage_position(symbol, atr_multiplier=1.0)
            else:
                logger.info("Waiting for market data..")
                time.sleep(5)    
                    
        except Exception as e:
            logger.error(f"Error in main workflow: {e}", exc_info=True)
            time.sleep(5)  # Add delay after error to prevent rapid retries

        # strategy.update_data(last_candle=price_data)
        # signal = strategy.generate_signal(price_data)


        # TODO : change to logger, or can even log it in the strategy
        # print(f"Signal: {signal}")
        # strategy.print_state()

        # I think this depends on the risk appetite of portfolio
        # amount = portfolio.calculate_position_size(signal, price_data)
        # portfolio.execute_trade(signal, amount, price_data)

        # time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    threading.Thread(target=start_binance, daemon=True).start()
    threading.Thread(target=start_subscriber, daemon=True).start()
    threading.Thread(target=signal_consumer_loop, daemon=True).start()
    threading.Thread(target=order_consumer_loop, daemon=True).start()
    # threading.Thread(target=lambda: asyncio.run(run_trade_analysis()), daemon=True).start()
    main()