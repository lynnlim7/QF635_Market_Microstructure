import pandas as pd
import numpy as np

from backtesting import Strategy, Backtest
from backtesting.lib import crossover
from app.utils.config import settings

def compute_MACD(close, fast, slow, signal):
    close_price = pd.Series(close)
    ema_fast = close_price.ewm(span=fast, adjust=False).mean()
    ema_slow = close_price.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd.values, signal_line.values


def compute_MACD(close, fast, slow, signal):
    """Compute MACD with standard EMA calculation"""
    close_price = pd.Series(close)
    ema_fast = close_price.ewm(span=fast, adjust=False).mean()
    ema_slow = close_price.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd.values, signal_line.values

class DualMACDStrategy(Strategy):
    # MACD parameters
    # Fast MACD (3,10,16)
    fast_period_1 = 3
    slow_period_1 = 10
    signal_1 = 16
    # Slow MACD (12,26,9)
    fast_period_2 = 12
    slow_period_2 = 26
    signal_2 = 9

    def init(self):
        close = self.data.Close
        
        # Fast MACD
        self.fast_macd, self.fast_signal = self.I(compute_MACD, close, 
                                                 self.fast_period_1, self.slow_period_1, self.signal_1)
        
        # Slow MACD
        self.slow_macd, self.slow_signal = self.I(compute_MACD, close, 
                                                 self.fast_period_2, self.slow_period_2, self.signal_2)

        self.latest_fast_macd = None
        self.latest_fast_signal = None
        self.latest_slow_macd = None
        self.latest_slow_signal = None
        self.last_action = None

        if len(self.fast_macd) > 0:
            self.latest_fast_macd = self.fast_macd[0]
            self.latest_fast_signal = self.fast_signal[0]
            self.latest_slow_macd = self.slow_macd[0]
            self.latest_slow_signal = self.slow_signal[0]

    def next(self):
        self.latest_fast_macd = self.fast_macd[-1]
        self.latest_fast_signal = self.fast_signal[-1]
        self.latest_slow_macd = self.slow_macd[-1]
        self.latest_slow_signal = self.slow_signal[-1]
        
        signal = self.generate_signal()
        
        if signal == settings.SIGNAL_SCORE_BUY and self.position.size == 0:
            self.buy()
            
        elif signal == settings.SIGNAL_SCORE_SELL and self.position.size != 0:
            self.position.close()
    
    def generate_signal(self) -> int:
        if (self.latest_fast_macd is None or self.latest_fast_signal is None or
            self.latest_slow_macd is None or self.latest_slow_signal is None):
            return settings.SIGNAL_SCORE_HOLD

        # BUY: Both MACDs are bullish (above their signal lines)
        fast_bullish = self.latest_fast_macd > self.latest_fast_signal
        slow_bullish = self.latest_slow_macd > self.latest_slow_signal
        
        if fast_bullish and slow_bullish and self.last_action != "BUY":
            self.last_action = "BUY"
            return settings.SIGNAL_SCORE_BUY

        # SELL: Either MACD is bearish (below its signal line)
        fast_bearish = self.latest_fast_macd < self.latest_fast_signal
        slow_bearish = self.latest_slow_macd < self.latest_slow_signal
        
        if (fast_bearish or slow_bearish) and self.last_action != "SELL":
            self.last_action = "SELL"
            return settings.SIGNAL_SCORE_SELL

        return settings.SIGNAL_SCORE_HOLD
    
    def get_state(self) -> dict:
        return {
            "fast_macd": self.latest_fast_macd,
            "fast_signal": self.latest_fast_signal,
            "slow_macd": self.latest_slow_macd,
            "slow_signal": self.latest_slow_signal,
            "last_action": self.last_action,
            "last_price": self.data.Close[-1]
        }