from bot.client.binance_api import BinanceApi
from bot.pricing.PricingEngine import PricingEngine
from bot.strategy.vwap_strategy import VWAPStrategy
import time



def main():

    symbol = "BTCUSDT" # potentially get multiple currency pairs
    api = BinanceApi()
    strategy = VWAPStrategy(symbol, api)
    engine = PricingEngine(api=api)


    while True:
        price_data = engine.get_latest_price(symbol)
        strategy.update_data(price_data)
        signal = strategy.generate_signal()

        # TODO : change to logger, or can even log it in the strategy
        print(f"Signal: {signal}")

        # I think this depends on the risk appetite of portfolio
        # amount = portfolio.calculate_position_size(signal, price_data)
        # portfolio.execute_trade(signal, amount, price_data)

        time.sleep(5)

if __name__ == "__main__":
    main()