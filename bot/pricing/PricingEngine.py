from bot.api.binance_gateway import BinanceGateway

class PricingEngine:
    def __init__(self, api: BinanceGateway):
        self.api = api


    # returns a series
    def get_latest_price(self, symbol: str):
        kline = self.api.get_ohlcv(symbol=symbol, interval="1m", limit=1)
        return kline.iloc[-1]