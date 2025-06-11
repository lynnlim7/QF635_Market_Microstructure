# from binance import SIDE_BUY, ORDER_TYPE_LIMIT, TIME_IN_FORCE_GTC
import threading
import time

from flask import Flask

from app.api.binance_api import BinanceApi
from app.api.binance_gateway import BinanceGateway
from app.portfolio.portfolio_manager import PortfolioManager
from app.risk.risk_manager import RiskManager
from app.routes import register_routes
from app.services import RedisPool
from app.strategy.base_strategy import BaseStrategy
from app.strategy.macd_strategy import MACDStrategy
from queue.signalqueue import SignalQueue
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

redis_pool = RedisPool()

## redis publisher 
publisher = redis_pool.create_publisher()
portfolio = PortfolioManager()
risk_manager = RiskManager(
    api=BinanceApi,
    portfolio_manager=portfolio,
    trade_signal=MACDStrategy(symbol),
    trade_direction=MACDStrategy(symbol)
)

gateway_instance: BinanceGateway | None = None
strategy_instance: BaseStrategy | None = None
binance_api = BinanceApi(settings.SYMBOL)

app = Flask(__name__)
register_routes(app, binance_api)

# Create global signal queue
signal_queue = SignalQueue()

def start_binance() -> None:
    logger.info("Starting binance now")
    global gateway_instance
    gateway_instance = BinanceGateway(symbol=symbol, redis_publisher=publisher)
    gateway_instance.connection()

# sample to handle, you can do your own
def handle_order_book_quote(data: dict):
    # logger.info(f"Receiving order book quote from redis!!: {data}")
    return

def handle_execution_updates(data: dict):
    logger.info(f"Receiving execution updates: {data}")

def start_subscriber():
    logger.info("Starting subscriber now")
    ## subscribe to redis channel
    subscriber = redis_pool.create_subscriber(redis_channels)
    # register handler for diff modules

    global strategy_instance
    while strategy_instance is None:
        logger.info("Waiting for strategy to start")
        time.sleep(1)
    logger.info("Strategy loaded")

    for channel in redis_channels:
        if "candlestick" in channel:
            subscriber.register_handler(channel, strategy_instance.update_data)

        if "execution" in channel:
            subscriber.register_handler(channel, handle_execution_updates)

        if "orderbook" in channel:
            subscriber.register_handler(channel, handle_order_book_quote)
        
    subscriber.start_subscribing()

def start_flask():
    # global app
    app.run(host="0.0.0.0", debug=True, use_reloader=False, port=8080)  # disable reloader in threaded mode

# Intermediate callback to push signals into the queue
def signal_callback(signal: int):
    logger.info(f"Signal pushed to queue: {signal}")
    signal_queue.push(signal)

def signal_consumer_loop():
    while True:
        if not signal_queue.is_empty():
            signal = signal_queue.pop()
            if signal is not None:
                risk_manager.accept_signal(signal)
        time.sleep(1) 

def main():
    logger.info(f"Start trading..")

    ## initialize modules
    try:
        global strategy_instance
        strategy_instance = MACDStrategy(symbol)
        strategy_instance.register_callback(signal_callback)
        ##Lynn: may not need this part
        #strategy_instance.register_callback(risk_manager.accept_signal)

        while True:
            orderbook_data = risk_manager.orderbook_df
            price_data = risk_manager.candlestick_df# candlestick dataframe
            if price_data is not None and len(price_data) != 0:
                # if len(price_data)>100:
                # logger.info(f"Current Candlestick: {price_data}")

                try:
                    vol = risk_manager.calculate_rolling_vol()
                    if vol is not None:
                        print(f"Volatility: {vol:.4f}")
                    else:
                        print(f"Not enough data..")
                    
                except Exception as e:
                    logger.error(f"Error calculating volatility: {e}")
                else:
                    logger.info("Waiting for candlestick data...")
                    time.sleep(5)
    except Exception as e:
        logger.error(f"Test interrupted: {e}", e)

        # strategy.update_data(last_candle=price_data)
        # signal = strategy.generate_signal(price_data)

        # TODO: pass signal into the risk manager


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
    main()