import pandas as pd
from binance import Client

from app.api.binance_api import BinanceApi
from app.strategy.base_strategy import BaseStrategy
from app.utils.config import settings

from app.utils.logger import setup_logger
from typing import Callable, List
from app.utils.logger import main_logger

macd_logger = setup_logger(
            logger_name="macd",
            logger_path="./logs/strategy",
            log_type="strategy",
            enable_console=False
            )

Callback = Callable[[int], None]

class MACDStrategy(BaseStrategy):
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
        main_logger.info(f"registering callback {callback.__name__}")
        self._callbacks.append(callback)
        main_logger.info(f"registered callback {callback.__name__}")

    def initialise_data(self):
        macd_logger.info("Initialising data now")

        if self.api is None:
            raise RuntimeError("Binance Gateway not initialised yet, please initialise it first before instantiating the strategy")

        # Fetch the initial close prices and load them into a DataFrame
        self.data = self.api.get_close_prices_df(symbol=self.symbol, interval=Client.KLINE_INTERVAL_1MINUTE, limit=200)

        if self.data is None or len(self.data) == 0:
            macd_logger.warning("No initial data loaded. Will wait for incoming candles to build indicators.")
            # Initialize empty dataframe with expected columns so update_data works
            self.data = pd.DataFrame(columns=['timestamp', 'close', 'EMA_FAST', 'EMA_SLOW', 'MACD', 'Signal_Line'])
            return  # Don't compute signals yet

        self.data = self.data.copy()

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

    def update_data(self, last_candle: dict):
        """
        Update the strategy with the latest data.
        This function appends the latest close price and recalculates the MACD and Signal Line.
        """
        if not last_candle['is_closed']:
            return

        if len(self.data) > 0:
            previous_data = self.data.iloc[-1]
            if previous_data['timestamp'] == last_candle['start_time']:
                macd_logger.info('[updateData] already added, will not add')
                return

        new_data = pd.DataFrame({'timestamp': [last_candle['start_time']], 'close': [last_candle['close']]})
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
        if self.latest_macd is None or self.latest_signal_line is None:
            return settings.SIGNAL_SCORE_HOLD  # Not enough data

        # Signal Generation Logic
        if self.latest_macd > self.latest_signal_line and self.last_action != "BUY":
            macd_logger.info(f"[Signal]: Buy signal triggered. state: {self.get_state()}")
            self.last_action = "BUY"
            return settings.SIGNAL_SCORE_BUY

        elif self.latest_macd < self.latest_signal_line and self.last_action != "SELL":
            macd_logger.info(f"[Signal]: Sell signal triggered. state: {self.get_state()}")
            self.last_action = "SELL"
            return settings.SIGNAL_SCORE_SELL

        return 0

    def get_state(self) -> dict:
        return {
            "symbol": self.symbol,
            "macd": self.latest_macd,
            "signal_line": self.latest_signal_line,
            "last_action": self.last_action,
            "last_price": self.data.iloc[-1]['close']
        }

    def print_state(self):
        macd_logger.info(f"[State] {self.get_state()}")