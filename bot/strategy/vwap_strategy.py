import pandas as pd
from numpy.random import get_state

from bot.client.binance_api import BinanceApi
from bot.strategy.base_strategy import BaseStrategy


# implements a rolling VWAP, length of 50
# NOTE: i don't think its working yet, a bit buggy
class VWAPStrategy(BaseStrategy):
    def __init__(self, symbol: str, api: BinanceApi, window: int = 200):
        self.symbol = symbol
        self.window = window
        self.data = pd.DataFrame()

        # load the other data
        self.on_init(api)

    def on_init(self, api: BinanceApi):
        print("loading historical data now")
        raw = api.client.get_klines(symbol=self.symbol, interval="1m", limit=self.window)
        df = pd.DataFrame(raw, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
        ])
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        self.update_data(df)


    def update_data(self, data):
        """Update the rolling VWAP with new price data."""
        if isinstance(data, dict):
            data = pd.DataFrame([data])

        self.data = pd.concat([self.data, data])
        self.data = self.data.tail(self.window)  # trim to rolling window

        pv = self.data["close"] * self.data["volume"]
        self.data["vwap"] = pv.rolling(window=self.window).sum() / self.data["volume"].rolling(window=self.window).sum()

    def generate_signal(self) -> int:
        """Generate a signal based on latest price vs VWAP."""
        if len(self.data) < self.window or "vwap" not in self.data:
            return 0

        close = self.data["close"].iloc[-1]
        vwap = self.data["vwap"].iloc[-1]

        if pd.isna(vwap):
            return 0  # Not enough data for full window

        if close < vwap:
            return 1
        elif close > vwap:
            return -1
        else:
            return 0

    def get_state(self) -> dict:
        if self.data.empty or "vwap" not in self.data:
            return {}
        return {
            "last_close": self.data["close"].iloc[-1],
            "last_vwap": self.data["vwap"].iloc[-1],
        }
