# from binance import SIDE_BUY, ORDER_TYPE_LIMIT, TIME_IN_FORCE_GTC
from bot.client.binance_api import BinanceApi
from bot.api.binance_gateway import BinanceGateway
# from bot.pricing.PricingEngine import PricingEngine
from bot.risk.risk_manager import RiskManager
from bot.portfolio.PortfolioManager import PortfolioManager
from bot.strategy.macd_strategy import MACDStrategy
from bot.strategy.vwap_strategy import VWAPStrategy
from bot.services.redis_sub import RedisSubscriber
from bot.services.redis_pub import RedisPublisher
from bot.utils.config import settings
from bot.utils.logger import setup_logger
import time
import threading
import os

symbol = "BTCUSDT" # TODO: potentially get multiple currency pairs

## list of redis channels
redis_channels = [
    f"{settings.REDIS_PREFIX}:candlestick:{symbol.lower()}"
    # add in other channels 
    ]

## redis publisher 
publisher = RedisPublisher()

portfolio = PortfolioManager()
risk_manager = RiskManager(
    candlestick={},
    portfolio_manager=portfolio
)

def start_binance():
    gateway = BinanceGateway(symbol=symbol, redis_publisher=publisher)
    gateway.connection()

def start_subscriber():
    ## subscribe to redis channel
    subscriber = RedisSubscriber(redis_channels)
    # register handler for diff modules
    for channel in redis_channels:
        if "candlestick" in channel:
            subscriber.register_handler(channel, risk_manager.process_candlestick)
        
    subscriber.start_subscribing()


def main():
    print(f"Start trading..")

    ## initialize modules
    # api = BinanceApi()
    # strategy = MACDStrategy(symbol, api)
    # engine = PricingEngine(api=api)
    try:
        while True:
            price_data = risk_manager.candlestick # candlestick dataframe
            if price_data is not None:
                # if len(price_data)>100:
                print(f"Current Candlestick: {price_data}")

                try:
                    vol = risk_manager.calculate_volatility()
                    if vol is not None:
                        print(f"Volatility: {vol:.4f}")
                    else:
                        print(f"Not enough data..")
                    
                except Exception as e:
                    print(f"Error calculating volatility: {e}")
                else:
                    print("Waiting for candlestick data...")
                    time.sleep(5)
    except Exception as e:
        print(f"Test interrupted: {e}")

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
    threading.Thread(target=start_binance, daemon=True).start()
    threading.Thread(target=start_subscriber, daemon=True).start()

    main()