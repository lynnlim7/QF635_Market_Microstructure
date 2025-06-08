import numpy as np 
import pandas as pd
from app.utils.logger import setup_logger
from app.utils.config import settings
from app.utils.logger import main_logger
from binance.client import Client
from app.portfolio.portfolio_manager import PortfolioManager
from app.strategy.macd_strategy import MACDStrategy
from app.api.binance_gateway import BinanceGateway
from app.api.binance_api import BinanceApi
from app.services.circuit_breaker import RedisCircuitBreaker

#TODO: explain thought process on take profit/ stop loss - should we sell everything? or pause trading
#TODO: listen to depth order book and take the mid price from best bid and ask
#TODO : dynamic take profit and stop loss - adjust take profit and stop loss pct based on market vol (multiples of ATR)
#TODO : rolling entropy to qc signal 

risk_logger = setup_logger(
            logger_name="risk",
            logger_path="./logs/risk",
            log_type="risk",
            enable_console=False
            )

class RiskManager:
    def __init__(self, 
                 api:BinanceApi,
                 circuit_breaker: RedisCircuitBreaker,
                 portfolio_manager:PortfolioManager,
                 trade_signal: MACDStrategy,
                 trade_direction: MACDStrategy,
                 max_risk_per_trade_pct:float = settings.MAX_RISK_PER_TRADE_PCT, 
                 max_absolute_drawdown:float = settings.MAX_ABSOLUTE_DRAWDOWN,
                 max_relative_drawdown:float = settings.MAX_RELATIVE_DRAWDOWN, 
                 ):
        self.orderbook_df = pd.DataFrame()
        self.candlestick_df= pd.DataFrame()
        self.api = api
        self.circuit_breaker = circuit_breaker
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
        
        self.orderbook_df = pd.concat([self.orderbook_df, row]).tail(500) # take latest 500

    # callback function from strategy - takes signal from queue
    def accept_signal(self, signal: int):
        main_logger.info(f"Received Signal from strategy: {signal}")

    # dynamic calculation of volatility adapted to mkt conditions
    def calculate_rolling_vol(self, window: int = 21):
        if len(self.orderbook_df)>1:
            log_returns = np.log(self.orderbook_df['mid_price']).diff()
            if log_returns.empty:
                return None
            self.rolling_vol = log_returns.rolling(window=window, min_periods=1).std() * np.sqrt(252)
            self.current_vol = self.rolling_vol.iloc[-1] if not self.rolling_vol.empty else None
            return self.current_vol
        return None

    # store rolling historical candlestick data as df 
    def process_candlestick(self, data: dict):
        risk_logger.info("Fetching live candlestick data..")
        if not data.get("is_closed", False):
            risk_logger.debug("Received incomplete candlestick. Skipping.")
            return

        risk_logger.info("Processing closed candlestick...")
        data['datetime'] = pd.to_datetime(data['start_time'], unit='ms')
        row = pd.DataFrame([data]).set_index('datetime')
            
        if self.candlestick_df.empty:
            self.candlestick_df = row
        else: 
            timestamp = row.index[0]
            if timestamp not in self.candlestick_df.index:
                self.candlestick_df = pd.concat([self.candlestick_df, row]).tail(500)
            else:
                self.candlestick_df.loc[data['datetime']] = row.iloc[0]

    # average true range - measure price vol of asset approx 14 days 
    def calculate_atr(self, period=14):
        if self.candlestick_df.empty:
            risk_logger.warning("No candlestick data available for ATR calculations.")
            return None 
        
        close = self.candlestick_df['close']
        high = self.candlestick_df['high']
        low = self.candlestick_df['low']
        prev_close = close.shift(1)
        high_low = high - low
        high_close = abs(high - prev_close)
        low_close = abs(low - prev_close)
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

        atr = true_range.rolling(window=period, min_periods=1).mean()
        return atr

    # dynamic position size 
    def calculate_position_size(self):
        atr = self.calculate_atr()
        if atr is None or atr.empty:
            risk_logger.warning("Unable to calculate ATR, using capital as default position size.")
            return self.portfolio_manager.get_cash()
        
        # one pos size per trade 
        latest_atr = atr.dropna().iloc[-1] 
        current_vol = self.calculate_rolling_vol()
        capital = self.portfolio_manager.get_cash()
        risk_amount = capital * self.max_risk_per_trade_pct
        position_size = risk_amount / latest_atr
        return position_size
    
    ## total portfolio risk
    def calculate_drawdown_limits(self, current_prices:dict, order) -> bool:
        current_value = self.portfolio_manager.get_total_portfolio_value(current_prices)
        if self.initial_value is None:
            self.initial_value = current_value # initial portfolio value 
        if self.peak_value is None or current_value>self.peak_value:
            self.peak_value = current_value
    
        relative_dd = (current_value - self.peak_value)/ self.peak_value
        absolute_dd = (self.initial_value - current_value)/ current_value
        
        if relative_dd > self.max_relative_drawdown or absolute_dd > self.max_absolute_drawdown:
            risk_logger.warning(f"Drawdown limits breached.")
            self.circuit_breaker.force_open(f"Drawdown limit breached. Relative dd: {relative_dd:.2%}, Absolute dd: {absolute_dd:.2%}.")
            for symbol, position in PortfolioManager.get_positions.items():
                qty = position['qty']
                try:
                    self.api.place_limit_order(
                        side="SELL",
                        qty=qty,
                        symbol=symbol
                    )
                # place market sell order - liquidate assets
                    risk_logger.info(f"Liquidated position for {symbol}:{qty} units.")
                except Exception as e:
                    risk_logger.error(f"Unable to liquidate position for {symbol}: {e}.")
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
        elif trade_direction == "SHORT":
            stop_loss = entry_price + sl_multi * atr
            take_profit = entry_price - sl_multi * atr 
        return take_profit, stop_loss

    def entry_position(self, current_price:float, current_prices:dict, api):
        signal_score = self.trade_signal.generate_signal()
        signal_direction = self.trade_directions(signal_score)

        if signal_direction == "HOLD":
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



        


        



        




    

    






    

