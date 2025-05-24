# from binance import SIDE_BUY, ORDER_TYPE_LIMIT, TIME_IN_FORCE_GTC
import threading
import time

from flask import Flask

from bot.api.binance_api import BinanceApi
from bot.api.binance_gateway import BinanceGateway
from bot.portfolio.PortfolioManager import PortfolioManager
from bot.risk.risk_manager import RiskManager
from bot.routes import register_routes
from bot.services.redis_pub import RedisPublisher
from bot.services.redis_sub import RedisSubscriber
from bot.strategy.base_strategy import BaseStrategy
from bot.strategy.macd_strategy import MACDStrategy
from bot.utils.config import settings
from bot.utils.func import get_execution_channel, get_orderbook_channel
from bot.utils.logger import set_basic_logger

symbol = settings.SYMBOL
logger = set_basic_logger("main")

## list of redis channels
redis_channels = [
    f"{settings.REDIS_PREFIX}:candlestick:{symbol.lower()}",
    get_orderbook_channel(symbol.lower()),
    get_execution_channel(symbol.lower())
    # add in other channels 
    ]

## redis publisher 
publisher = RedisPublisher()
portfolio = PortfolioManager()
risk_manager = RiskManager(
    candlestick={},
    portfolio_manager=portfolio
)

gateway_instance: BinanceGateway | None = None
strategy_instance: BaseStrategy | None = None
binance_api = BinanceApi(settings.SYMBOL)

app = Flask(__name__)
register_routes(app, binance_api)

def start_binance() -> None:
    logger.info("Starting binance now")
    global gateway_instance
    gateway_instance = BinanceGateway(symbol=symbol, redis_publisher=publisher)
    gateway_instance.connection()

# sample to handle, you can do your own
def handle_order_book_quote(data: dict):
    logger.info(f"Receiving order book quote from redis!!: {data}")

def handle_execution_updates(data: dict):
    logger.info(f"Receiving execution updates: {data}")

def start_subscriber():
    logger.info("Starting subscriber now")
    ## subscribe to redis channel
    subscriber = RedisSubscriber(redis_channels)
    # register handler for diff modules

    global strategy_instance
    while strategy_instance is None:
        logger.info("Waiting for strategy to start")
        time.sleep(1)

    for channel in redis_channels:
        if "candlestick" in channel:
            subscriber.register_handler(channel, risk_manager.process_candlestick)
            subscriber.register_handler(channel, strategy_instance.update_data)

        if "execution" in channel:
            subscriber.register_handler(channel, handle_execution_updates)

        if "orderbook" in channel:
            subscriber.register_handler(channel, handle_order_book_quote)
        
    subscriber.start_subscribing()

def start_flask():
    # global app
    app.run(debug=True, use_reloader=False, port=8080)  # disable reloader in threaded mode


def main():
    logger.info(f"Start trading..")

    ## initialize modules
    try:
        global strategy_instance
        strategy_instance = MACDStrategy(symbol)

        while True:
            price_data = risk_manager.candlestick # candlestick dataframe
            if price_data is not None and len(price_data) != 0:
                # if len(price_data)>100:
                logger.info(f"Current Candlestick: {price_data}")

                try:
                    vol = risk_manager.calculate_volatility()
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
    main()