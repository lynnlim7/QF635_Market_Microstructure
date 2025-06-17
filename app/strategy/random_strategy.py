import pandas as pd
import random

from app.api.binance_api import BinanceApi
from app.strategy.base_strategy import BaseStrategy
from app.utils.config import settings


from app.utils.logger import setup_logger
from typing import Callable, List
from app.utils.logger import main_logger as logger



Callback = Callable[[int], None]

class RandomStrategy(BaseStrategy):
    def __init__(self, symbol: str,
                 api:BinanceApi=None,
                 config=None):
        if config is None:
            config = {
                "slow_period": 26,
                "fast_period": 12,
                "signal_period": 9,
                "smoothing_factor": 2,
            }

        if api is None:
            self.api = BinanceApi(symbol)
        else:
            self.api = api

        self.symbol = symbol
        self.latest_macd = None
        self.latest_signal_line = None
        self.last_action = None  # Tracks last action: Buy, Sell, or Hold
        self.data = pd.DataFrame()
        self.config = config
        self._callbacks: List[Callback] = []

        self.initialise_data()
        self.print_state()

    def register_callback(self, callback: Callback):
        logger.info(f"registering callback {callback.__name__}")
        self._callbacks.append(callback)
        logger.info(f"registered callback {callback.__name__}")

    def initialise_data(self):
        logger.info("Initialising data now")
        # this is to initialise the last action so it won't instantly ask me to buy or sell in the first ticket
        self.generate_signal()

    def update_data(self, last_candle: dict):
        """
        Update the strategy with the latest data.
        This function appends the latest close price and recalculates the MACD and Signal Line.
        """
        # if not last_candle['is_closed']:
        #     return

        signal = self.generate_signal()
        print(f"Signal Generated: {signal}")
        for callback in self._callbacks:
            callback(signal)


    def generate_signal(self) -> int:
        """
        Generate trading signal based on MACD:
        - Buy when MACD crosses above the Signal Line
        - Sell when MACD crosses below the Signal Line
        """
        curr = random.choice([1,-1])
        if curr == 1 and self.last_action != "BUY":
            self.last_action = "BUY"
            return settings.SIGNAL_SCORE_BUY

        elif curr == -1 and self.last_action != "SELL":
            self.last_action = "SELL"
            return settings.SIGNAL_SCORE_SELL

        return 0

    def get_state(self) -> dict:
        return {
            "symbol": self.symbol,
            "last_action": self.last_action,
        }

    def print_state(self):
        logger.info(f"[State] {self.get_state()}")