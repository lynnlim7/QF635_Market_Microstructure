"""
Risk management system 
Dynamic, volatility adjusted position sizing that reduces exposure during volatile periods 
"""

import numpy as np 
import pandas as pd

from binance.client import Client
from bot.portfolio.PortfolioManager import PortfolioManager
from bot.strategy.macd_strategy import MACDStrategy
from bot.api.binance_gateway import BinanceGateway
from bot.utils.logger import setup_logger
from bot.utils.config import settings


#TODO: explain thought process on take profit/ stop loss - should we sell everything? or pause trading
#TODO: listen to depth order book and take the mid price from best bid and ask
#TODO : dynamic take profit and stop loss - adjust take profit and stop loss pct based on market vol (multiples of ATR)

risk_logger = setup_logger(
            logger_name="risk",
            logger_path="./logs/risk",
            log_type="risk",
            enable_console=False
)

class RiskManager:
    def __init__(self, 
                 api:BinanceGateway,
                 portfolio_manager:PortfolioManager,
                 trade_signal: MACDStrategy,
                 trade_direction: MACDStrategy,
                 max_risk_per_trade_pct:float = settings.MAX_RISK_PER_TRADE_PCT, 
                 max_absolute_drawdown:float = settings.MAX_ABSOLUTE_DRAWDOWN,
                 max_relative_drawdown:float = settings.MAX_RELATIVE_DRAWDOWN, 
                 ):
        # self.symbol = symbol
        self.orderbook_df = pd.DataFrame()
        self.candlestick_df= pd.DataFrame()
        self.api = api
        self.initial_value = None
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_absolute_drawdown = max_absolute_drawdown
        self.max_relative_drawdown = max_relative_drawdown
        self.peak_value = None
        self.portfolio_manager = portfolio_manager
        self.trade_signal = trade_signal
        self.trade_direction = trade_direction

    def data_aggregator(self, data:dict):
        risk_logger.info("Fetching orderbook data..")
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        timestamp = pd.to_datetime(data.get("timestamp", None), unit='ms')

        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
        mid_price = (best_ask + best_bid)/2
        spread = best_ask - best_bid
        spread_pct = spread/mid_price

        row = pd.DataFrame([{
            "timestamp": timestamp,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "spread": spread,
            "spread_pct": spread_pct
        }]).set_index("timestamp")
        
        self.orderbook_df = pd.concat([self.orderbook_df, row]).tail(500)


    # store rolling historical candlestick data as df - log returns and volatility
    def process_candlestick(self, data: dict):
        risk_logger.info("Fetching live candlestick data..")
        data['datetime'] = pd.to_datetime(data['start_time'], unit='ms')
        row = pd.DataFrame([data]).set_index('datetime')
            
        if self.candlestick.empty:
            self.candlestick = row
        else: 
            timestamp = row.index[0]
            if timestamp not in self.candlestick.index:
                self.candlestick_df = pd.concat([self.candlestick_df, row])
            else:
                self.candlestick_df.loc[data['datetime']] = row.iloc[0]
            

    # # realized vol
    # def calculate_volatility(self):
    #     print(f"Start calculating volatility..")
    #     close = self.candlestick_df['close']
    #     if len(close)>2:
    #         daily_return = np.log(close/close.shift(1)).dropna()
    #         std_dev = daily_return.rolling(window=30, min_periods=1).std()
    #         volatility = std_dev.iloc[-1]*np.sqrt(252)
    #         return volatility
    #     print(f"Not enough close prices..")


    # average true range - measure price vol of asset approx 14 days 
    def calculate_atr(self, period=14):
        close = self.candlestick_df['close']
        high = self.candlestick_df['high']
        low = self.candlestick_df['low']
        prev_close = close.shift(1)
        high_low = high - low
        high_close = abs(high-prev_close)
        low_close = abs(low-prev_close)
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        return atr

    # dynamic position size 
    def calculate_position_size(self):
        # risk amount is a fixed pct of capital
        capital = self.portfolio_manager.get_cash()
        risk_amount = capital * self.max_risk_per_trade_pct
        atr = self.calculate_atr()
        # one pos size per trade 
        latest_atr = atr.dropna().iloc[-1] 
        position_size = risk_amount / latest_atr
        print(f"Position size:{position_size}")
        return position_size
    
    ## total portfolio risk
    def calculate_drawdown_limits(self, current_prices:dict, order) -> bool:
        current_value = self.get_total_portfolio_value(current_prices)
        if self.initial_value is None:
            self.initial_value = current_value # initial portfolio value 
        if self.peak_value is None or current_value>self.peak_value:
            self.peak_value = current_value
    
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
        
    def trade_directions(self, trade_signal:int) -> str:
        if trade_signal == settings.SIGNAL_SCORE_BUY:
            return "BUY"
        elif trade_signal == settings.SIGNAL_SCORE_SELL:
            return "SELL"
        return "HOLD"
    
    def calc_tp_sl(self, entry_price:float, atr:float, trade_direction:str, sl_multi=1.0, tp_multi=2.0):
        if trade_direction == "LONG":
            stop_loss = entry_price - sl_multi * atr
            take_profit = entry_price + sl_multi * atr
        if trade_direction == "SHORT":
            stop_loss = entry_price + sl_multi * atr
            take_profit = entry_price - sl_multi * atr 

    def entry_position(self, current_price:float, current_prices:dict, api):
        signal_score = self.trade_signal.generate_signal()
        signal_direction = self.trade_direction(signal_score)

        if signal_score == "HOLD":
            risk_logger.info("No entry signal.")
            return 
        
        if self.calculate_drawdown_limits(current_prices, order=None) is False:
            risk_logger.info("Drawdown limit breached, trade entry blocked.")
            return 
        
        if not self.orderbook_df.empty:
            entry_price = self.orderbook_df['mid_price'].iloc[-1]
        else: 
            risk_logger.info("Unable to get orderbook data.")
            return
        
        atr = self.calculate_atr()
        # realized_vol = self.calculate_volatility(window=30)
        stop_loss, take_profit = self.calc_tp_sl(entry_price, atr, signal_direction)

        self.active_trades = {
            "trade_direction": signal_direction, 
            "stop_loss": stop_loss,
            "take_profit": take_profit
        }

        return stop_loss, take_profit
    
    def manage_position(self, current_price:float, current_prices:dict):
        if self.active_trades is None:
            risk_logger.info("No active trades to monitor.")
            return

        active_trades = self.active_trades()

        trade_direction = active_trades["trade_direction"]
        stop_loss = active_trades["stop_loss"]
        take_profit = active_trades["take_profit"]

        if trade_direction == "BUY":
            if (current_price <= stop_loss) or (current_price >= take_profit):
                risk_logger.info("Take profit/ Stop loss hit, exiting long position..")
                self.close_position("SELL", current_price)
                return
        elif trade_direction == "SELL":
            if (current_price >= stop_loss) or (current_price <= take_profit):
                risk_logger.info("Take profit/ Stop loss hit, exiting short position..")
                self.close_poition("BUY", current_price)
                return



        


        



        




    

    






    

