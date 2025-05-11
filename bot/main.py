from binance import SIDE_BUY, ORDER_TYPE_LIMIT, TIME_IN_FORCE_GTC

from bot.client.binance_api import BinanceApi
from bot.pricing.PricingEngine import PricingEngine
from bot.strategy.vwap_strategy import VWAPStrategy
import time



def main():

    symbol = "BTCUSDT" # TODO: potentially get multiple currency pairs
    api = BinanceApi()
    # api.get_account()
    strategy = VWAPStrategy(symbol, api)
    engine = PricingEngine(api=api)


    while True:
        price_data = engine.get_latest_price(symbol)
        strategy.update_data(price_data)
        signal = strategy.generate_signal()

        # TODO : change to logger, or can even log it in the strategy
        print(f"Signal: {signal}")

        # TODO: pass signal into the risk manager


        # I think this depends on the risk appetite of portfolio
        # amount = portfolio.calculate_position_size(signal, price_data)
        # portfolio.execute_trade(signal, amount, price_data)

        time.sleep(5)

if __name__ == "__main__":
    main()