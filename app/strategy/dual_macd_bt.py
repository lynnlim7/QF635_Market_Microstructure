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

   

class BacktestingRiskManager:
    def __init__(self, strategy, max_risk_per_trade_pct=0.01, max_exposure_pct=0.05):
        self.strategy = strategy
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_exposure_pct = max_exposure_pct
        
        # Track portfolio state
        self.initial_capital = 100000
        self.peak_value = 100000
        self.current_exposure = 0
        
    def calculate_atr(self, high, low, close, period=14):
        """Vectorized ATR calculation"""
        prev_close = pd.Series(close).shift(1)
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return true_range.rolling(window=period, min_periods=1).mean()
    
    def calculate_position_size(self, entry_price, atr_value):
        """Calculate position size based on ATR"""
        if atr_value <= 0:
            return 0
            
        risk_amount = entry_price * self.max_risk_per_trade_pct
        position_size = (risk_amount / atr_value) / 1000
        return max(position_size, 0)
    
    def check_exposure_limit(self, position_size, current_price):
        """Check if position exceeds exposure limit"""
        position_value = abs(position_size * current_price)
        portfolio_value = self.strategy.equity
        max_exposure = portfolio_value * self.max_exposure_pct
        
        return position_value <= max_exposure
    
    def calculate_tp_sl(self, entry_price, atr_value, position_size, atr_multiplier=1.0):
        """Calculate take profit and stop loss levels"""
        if atr_value <= 0:
            return None, None
            
        risk = atr_value * atr_multiplier
        
        if position_size > 0:  # Long position
            stop_loss = entry_price - risk
            take_profit = entry_price + (2 * risk)
        else:  # Short position
            stop_loss = entry_price + risk
            take_profit = entry_price - (2 * risk)
            
        return take_profit, stop_loss
    
    def check_drawdown_limit(self, current_equity):
        """Check drawdown limits"""
        self.peak_value = max(self.peak_value, current_equity)
        drawdown = (self.peak_value - current_equity) / self.peak_value
        
        # Emergency shutdown if drawdown > 10%
        if drawdown > 0.10:
            return True
        return False

class DualMACD(Strategy):
    # fast MACD (3,10,16)
    fast_period_1 = 3
    slow_period_1 = 10
    signal_1 = 16
    # slow MACD (12,26,9)
    fast_period_2 = 12
    slow_period_2 = 26
    signal_2 = 9

    def init(self):
        close = self.data.Close

        self.fast_macd, self.fast_signal = self.I(compute_MACD, close, self.fast_period_1, self.slow_period_1, self.signal_1)
        self.slow_macd, self.slow_signal = self.I(compute_MACD, close, self.fast_period_2, self.slow_period_2, self.signal_2)

        self.atr = self.I(self.calculate_atr_vectorized, self.data.High, self.data.Low, self.data.Close)

        self.risk_manager = BacktestingRiskManager(self)
        self.entry_price = None
        self.take_profit = None
        self.stop_loss = None
        self.emergency_shutdown = False

    def calculate_atr_vectorized(self, high, low, close, period=14):
        """Simplified ATR calculation"""
        # Use numpy arrays directly
        high_arr = np.array(high)
        low_arr = np.array(low)
        close_arr = np.array(close)
        
        # Calculate true range
        prev_close = np.roll(close_arr, 1)
        prev_close[0] = close_arr[0]  # Handle first element
        
        tr1 = high_arr - low_arr
        tr2 = np.abs(high_arr - prev_close)
        tr3 = np.abs(low_arr - prev_close)
        
        # True range is max of the three
        true_range = np.maximum(tr1, np.maximum(tr2, tr3))
        
        # Calculate ATR using pandas rolling
        atr_series = pd.Series(true_range).rolling(window=period, min_periods=1).mean()
        
        return atr_series.values
        
    
    def next(self):
        fast_bullish = self.fast_macd[-1] > self.fast_signal[-1]
        slow_bullish = self.slow_macd[-1] > self.slow_signal[-1]
        fast_bearish = self.fast_macd[-1] < self.fast_signal[-1]
        slow_bearish = self.slow_macd[-1] < self.slow_signal[-1]

        if not self.position and fast_bullish and slow_bullish:
            self.buy()

        elif self.position and (fast_bearish or slow_bearish):
            self.position.close()