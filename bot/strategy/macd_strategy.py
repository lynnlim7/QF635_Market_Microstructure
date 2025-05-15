import numpy as np
import pandas as pd
from binance import Client
from numpy.random import get_state

from bot.client.binance_api import BinanceApi
from bot.strategy.base_strategy import BaseStrategy





class MACDStrategy(BaseStrategy):
    def __init__(self, symbol: str,
                 api: BinanceApi,
                 config=None):
        if config is None:
            config = {
                "slow_period": 26,
                "fast_period": 12,
                "signal_period": 9,
                "smoothing_factor": 2,
            }
        self.api = api
        self.symbol = symbol
        self.latest_macd = None
        self.latest_signal_line = None
        self.last_action = None  # Tracks last action: Buy, Sell, or Hold
        self.data = pd.DataFrame()
        self.config = config

        self.initialise_data()
        self.print_state()


    def initialise_data(self):
        # Fetch the initial close prices and load them into a DataFrame
        self.data = self.api.get_close_prices_df(symbol=self.symbol, interval=Client.KLINE_INTERVAL_1MINUTE, limit=200)

        # Calculate MACD and Signal Line for the initial data
        self.data['EMA_FAST'] = self.data['close'].ewm(span=self.config['fast_period'], adjust=False).mean()
        self.data['EMA_SLOW'] = self.data['close'].ewm(span=self.config['slow_period'], adjust=False).mean()

        self.data['MACD'] = self.data['EMA_FAST'] - self.data['EMA_SLOW']
        self.data['Signal_Line'] = self.data['MACD'].ewm(span=self.config['signal_period'], adjust=False).mean()

        # Set the initial MACD and Signal Line values
        self.latest_macd = self.data['MACD'].iloc[-1]
        self.latest_signal_line = self.data['Signal_Line'].iloc[-1]

        # this is to initialise the last action so it won't instantly ask me to buy or sell in the first ticket
        self.generate_signal()

    def update_data(self, last_candle):
        """
        Update the strategy with the latest data.
        This function appends the latest close price and recalculates the MACD and Signal Line.
        """
        previous_data = self.data.iloc[-1]
        if previous_data['timestamp'] == last_candle['timestamp']:
            print('already added, will not add')
            return

        new_data = pd.DataFrame({'timestamp': [last_candle['timestamp']], 'close': [last_candle['close']]})
        self.data = pd.concat([self.data, new_data], ignore_index=True)

        new_close = last_candle['close']
        smoothing_factor = self.config['smoothing_factor']
        alpha_fast = smoothing_factor / (self.config['fast_period'] + 1)  # Fast EMA (12-period)
        alpha_slow = smoothing_factor / (self.config['slow_period'] + 1)  # Slow EMA (26-period)
        alpha_signal = smoothing_factor / (self.config['signal_period'] + 1) # Signal period (9-period)

        previous_fast_ema = self.data['EMA_FAST'].iloc[-2] if len(self.data) > 1 else new_close
        previous_slow_ema = self.data['EMA_SLOW'].iloc[-2] if len(self.data) > 1 else new_close

        # Incrementally update the Fast and Slow EMAs
        fast_ema = alpha_fast * new_close + (1 - alpha_fast) * previous_fast_ema
        slow_ema = alpha_slow * new_close + (1 - alpha_slow) * previous_slow_ema

        # Recalculate the MACD (Fast EMA - Slow EMA)
        macd = fast_ema - slow_ema

        # Recalculate the Signal Line (9-period EMA of the MACD)
        if self.latest_signal_line is not None:
            # Update Signal Line using the EMA formula (Signal Line is EMA of MACD)
            signal_line = alpha_signal * macd + (1 - alpha_signal) * self.latest_signal_line
        else:
            # For the first update, set the Signal Line equal to the MACD
            signal_line = macd

        self.latest_macd = macd
        self.latest_signal_line = signal_line

        # Add the new MACD and Signal Line to the DataFrame
        self.data.loc[self.data.index[-1], 'EMA_FAST'] = fast_ema
        self.data.loc[self.data.index[-1], 'EMA_SLOW'] = slow_ema
        self.data.loc[self.data.index[-1], 'MACD'] = macd
        self.data.loc[self.data.index[-1], 'Signal_Line'] = signal_line



    def generate_signal(self) -> int:
        """
        Generate trading signal based on MACD:
        - Buy when MACD crosses above the Signal Line
        - Sell when MACD crosses below the Signal Line
        """
        if self.latest_macd is None or self.latest_signal_line is None:
            return 0  # Not enough data

        # Signal Generation Logic
        if self.latest_macd > self.latest_signal_line and self.last_action != "BUY":
            self.last_action = "BUY"
            return 1

        elif self.latest_macd < self.latest_signal_line and self.last_action != "SELL":
            self.last_action = "SELL"
            return -1

        return 0

    def get_state(self) -> dict:
        return {
            "symbol": self.symbol,
            "macd": self.latest_macd,
            "signal_line": self.latest_signal_line,
            "last_action": self.last_action,
            "last_price": self.data.iloc[-1]
        }

    def print_state(self):
        print(f"Current state: {self.get_state()}")
