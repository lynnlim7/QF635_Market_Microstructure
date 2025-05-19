from binance.client import Client
from bot.portfolio.PortfolioManager import PortfolioManager
from bot.utils.logger import setup_logger
from bot.utils.config import settings
import numpy as np 
import orjson
import redis
import threading

 #TODO: explain thought process on take profit/ stop loss - should we sell everything?

class RiskManager:
    def __init__(self, 
                 candlestick:dict,
                 portfolio_manager:PortfolioManager,
                 max_risk_per_trade_pct:float = settings.MAX_RISK_PER_TRADE_PCT, 
                 max_absolute_drawdown:float = settings.MAX_ABSOLUTE_DRAWDOWN,
                 max_relative_drawdown:float = settings.MAX_RELATIVE_DRAWDOWN, 
                 ):
        self.candlestick = None
        self.initial_value = None
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_absolute_drawdown = max_absolute_drawdown
        self.max_relative_drawdown = max_relative_drawdown
        self.peak_value = None
        self.portfolio_manager = portfolio_manager

    def process_candlestick(self, data: dict):
        self.candlestick = data # candlestick data
    
    # TODO : fix volatility calculation to deal with series and not float 
    def calculate_volatility(self):
        close = self.candlestick['close']
        daily_return = np.log(close/close.shift(1))
        volatility = daily_return.rolling(window=50).std() * np.sqrt(252)
        return volatility
    
    def calculate_position_size(self, volatility, capital):
        # risk amount is a fixed pct of capital
        capital = self.portfolio_manager.get_cash()
        risk_amount = capital * self.max_risk_per_trade_pct
        # position size inverse of volatility
        position_size = risk_amount / volatility
        return position_size
    
    def calculate_drawdown_limits(self, current_prices:dict, order) -> bool:
        current_value = self.get_total_portfolio_value(current_prices)
        if self.initial_value is None:
            self.initial_value = current_value # initial portfolio value 
        if self.peak_value is None or current_value>self.peak_value:
            self.peak_value = current_value
        # relative drawdown = trough-peak/peak 
        relative_dd = (current_value - self.peak_value)/ self.peak_value
        absolute_dd = (self.initial_value - current_value)/ current_value
        
        if relative_dd > self.max_relative_drawdown or absolute_dd > self.max_absolute_drawdown:
            print(f"Drawdown threshold breached")
            for symbol, position in PortfolioManager.get_positions.items():
                qty = position['qty']
                # place market sell order - liquidate assets
                order = Client.order_market_sell(symbol, qty)
            return False
        else:
            return True 
        




    

    






    

