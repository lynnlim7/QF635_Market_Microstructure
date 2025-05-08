from bot.client.binance_api import BinanceApi

class PricingEngine:
    def __init__(self, api: BinanceApi):
        self.api = api

    def get_latest_price(self, symbol: str):
        kline = self.api.client.get_klines(symbol=symbol, interval="1m", limit=1)[0]
        market_data = {
            "timestamp": kline[0],
            "close": float(kline[4]),
            "volume": float(kline[5])
        }
        self.api.market_logger.info(market_data)
        return market_data