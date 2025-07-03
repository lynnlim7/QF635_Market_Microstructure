from backtesting import Strategy, Backtest
import pandas as pd
import numpy as np
from app.utils.config import settings
class MACDStrategyBacktest(Strategy):
    slow_period = 26
    fast_period = 12
    signal_period = 9
    smoothing_factor = 2
    
    def init(self):
        self.ema_fast = self.I(self.compute_ema_with_smoothing, self.data.Close, self.fast_period, self.smoothing_factor)
        self.ema_slow = self.I(self.compute_ema_with_smoothing, self.data.Close, self.slow_period, self.smoothing_factor)
        
        self.macd = self.ema_fast - self.ema_slow
        self.signal_line = self.I(self.compute_ema_with_smoothing, self.macd, self.signal_period, self.smoothing_factor)
        

        self.latest_macd = None
        self.latest_signal_line = None
        self.last_action = None

        if len(self.macd) > 0:
            self.latest_macd = self.macd[0]
            self.latest_signal_line = self.signal_line[0]
            self.generate_signal()
    
    def compute_ema_with_smoothing(self, data, period, smoothing_factor):
        alpha = smoothing_factor / (period + 1)
        return pd.Series(data).ewm(alpha=alpha, adjust=False).mean().values
    
    def next(self):
        self.latest_macd = self.macd[-1]
        self.latest_signal_line = self.signal_line[-1]
        
        signal = self.generate_signal()
        
        # Execute trades
        if signal == settings.SIGNAL_SCORE_BUY and not self.position:
            self.buy()
            
        elif signal == settings.SIGNAL_SCORE_SELL and self.position:
            self.position.close()
    
    def generate_signal(self) -> int:
  
        if self.latest_macd is None or self.latest_signal_line is None:
            return settings.SIGNAL_SCORE_HOLD 

        if self.latest_macd > self.latest_signal_line and self.last_action != "BUY":
            self.last_action = "BUY"
            return settings.SIGNAL_SCORE_BUY

        elif self.latest_macd < self.latest_signal_line and self.last_action != "SELL":
            self.last_action = "SELL"
            return settings.SIGNAL_SCORE_SELL

        return settings.SIGNAL_SCORE_HOLD
    
    def get_state(self) -> dict:
        return {
            "macd": self.latest_macd,
            "signal_line": self.latest_signal_line,
            "last_action": self.last_action,
            "last_price": self.data.Close[-1]
        }
    
