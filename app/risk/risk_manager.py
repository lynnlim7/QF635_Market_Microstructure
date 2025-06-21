import numpy as np 
import pandas as pd
from binance import Client
from app.utils.config import settings
from app.utils.logger import main_logger as logger
from app.portfolio.portfolio_manager import PortfolioManager
from app.api.binance_api import BinanceApi
from app.services.circuit_breaker import RedisCircuitBreaker
import threading, time

#TODO: explain thought process on take profit/ stop loss - should we sell everything? or pause trading
#TODO: listen to depth order book and take the mid price from best bid and ask
#TODO : dynamic take profit and stop loss - adjust take profit and stop loss pct based on market vol (multiples of ATR)
#TODO : handle market order (default) and limit order (fill up price)
#TODO : call binance to creater order if receive buy signal - how much to buy?

class RiskManager:
    def __init__(self, 
                 symbol: str,
                 api:BinanceApi,
                 portfolio_manager:PortfolioManager,
                 circuit_breaker: RedisCircuitBreaker,
                 max_risk_per_trade_pct:float = settings.MAX_RISK_PER_TRADE_PCT, 
                 max_absolute_drawdown:float = settings.MAX_ABSOLUTE_DRAWDOWN,
                 max_relative_drawdown:float = settings.MAX_RELATIVE_DRAWDOWN, 
                 max_exposure_pct:float = settings.MAX_EXPOSURE_PCT,
                 ):
        self.api = api
        self.symbol = symbol
        self.portfolio_manager = portfolio_manager
        self.circuit_breaker = circuit_breaker
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_absolute_drawdown = max_absolute_drawdown
        self.max_relative_drawdown = max_relative_drawdown
        self.max_exposure_pct = max_exposure_pct


        self.active_trades = {}
        self.df_orderbook = {}  
        self.df_candlestick = {}  
        self.current_value = 0.0
        self.current_position_size = None
        self.current_atr = None

    def on_new_orderbook(self, data:dict):
        if not isinstance(data, dict):
            logger.warning(f"Invalid data format for orderbook: {data}")
            return
            
        logger.info("Processing orderbook data.")

        timestamp = pd.to_datetime(data.get("timestamp", None), unit='ms')
        symbol = data.get('contract_name', self.symbol).upper()  
        
        logger.info(f"Processing orderbook for symbol: {symbol}")

        bids = data.get('bids', [])
        asks = data.get('asks', [])
        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
        mid_price = (best_ask + best_bid)/2
        spread = best_ask - best_bid
        spread_pct = spread/mid_price
           
        row = pd.DataFrame([{
            "timestamp": timestamp,
            "symbol": symbol,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "spread": spread,
            "spread_pct": spread_pct
        }]).set_index("timestamp")
            
        if symbol not in self.df_orderbook:
            self.df_orderbook[symbol] = row
            logger.info(f"Created new orderbook entry for symbol: {symbol}")
        else:
            self.df_orderbook[symbol] = pd.concat([self.df_orderbook[symbol], row]).tail(500)
            logger.info(f"Updated orderbook for symbol: {symbol}")

        self.calculate_position_size()
        # self.manage_position(symbol)
           
    def on_new_candlestick(self, data):
        logger.info("Processing new candlestick data.")
        # if not data.get('is_closed', False):
        #     logger.info("Received incomplete candle, skipping processing.")
        #     return
        if isinstance(data, dict):
            symbol = data.get('symbol', self.symbol).upper()
            timestamp = pd.to_datetime(data['start_time'], unit='ms')

            df_candlestick = pd.DataFrame([{
                'timestamp': timestamp,
                'open': float(data['open']),
                'high': float(data['high']),
                'low': float(data['low']),
                'close': float(data['close']),
                'volume': float(data['volume']),
                'is_closed': True # get full candle
            }]).set_index('timestamp')
            
            if symbol not in self.df_candlestick:
                self.df_candlestick[symbol] = df_candlestick
            else:
                self.df_candlestick[symbol] = pd.concat([self.df_candlestick[symbol], df_candlestick]).tail(500)

            self.calculate_atr()
            # self.calculate_drawdown_limits(symbol)
    
    # average true range - measure price vol of asset approx 14 days 
    def calculate_atr(self, period=14):
        if self.symbol not in self.df_candlestick or self.df_candlestick[self.symbol].empty:
            logger.warning(f"No candlestick data available for {self.symbol} for ATR calculations.")
            return None 
        
        try:
            df = self.df_candlestick[self.symbol]
            if 'close' not in df.columns or 'high' not in df.columns or 'low' not in df.columns:
                logger.warning(f"Missing required columns in candlestick data for {self.symbol}")
                return None

            close = df['close']
            high = df['high']
            low = df['low']
            prev_close = close.shift(1)
            high_low = high - low
            high_close = abs(high - prev_close)
            low_close = abs(low - prev_close)
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

            atr = true_range.rolling(window=period, min_periods=1).mean()

            self.current_atr = float(atr.iloc[-1]) if not atr.empty else None
   
            if self.current_atr is not None and self.current_atr > 0:
                if self.symbol in self.df_orderbook and not self.df_orderbook[self.symbol].empty:
                    self.calculate_position_size()
            return atr

        except Exception as e:
            logger.error(f"Error calculating ATR for {self.symbol}: {e}", exc_info=True)
            self.current_atr = None

    # dynamic position size 
    # should be based on current existing positions - net positions? 
    def calculate_position_size(self) -> float:

        if self.current_atr is None or self.current_atr <= 0:
            logger.warning("Unable to calculate ATR. Skipping position sizing and trade.")
            return

        if self.symbol not in self.df_orderbook or self.df_orderbook[self.symbol].empty:
            logger.warning(f"No orderbook data available for {self.symbol}")
            return

        try:
            entry_price = self.df_orderbook[self.symbol]['mid_price'].iloc[-1]
            if entry_price <= 0:
                logger.warning(f"Invalid entry price: {entry_price}")

            risk_amount = entry_price * self.max_risk_per_trade_pct
            position_size = (risk_amount / self.current_atr)/1000
            logger.info(f"Calculated position size: {position_size:.4f} with entry price: {entry_price:.4f} and ATR: {self.current_atr:.4f}")
            # # TODO: CHECK WHY SO BIG?
            self.current_position_size = position_size
            return position_size
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}", exc_info=True)
            self.current_position_size = None

    def trade_directions(self, signal:int) -> str:
        if signal == settings.SIGNAL_SCORE_BUY:
            return "BUY"
        elif signal == settings.SIGNAL_SCORE_SELL:
            return "SELL"
        return "HOLD"
    
    def accept_signal(self, signal: int, symbol: str) :
        if signal is None:
            logger.info("No signal received from queue.")
            return
        logger.info(f"=====RECEIVED SIGNAL UPDATE=====: {signal} for {symbol}")

    def entry_position(self, symbol: str, direction: str = None, size:float):
        try:
            self.api.place_market_order(
            symbol=symbol,
            side=direction,
            qty=size,
            )
        except Exception as e:
            logger.error(f"Failed to place market order for {symbol}: {e}")
            return None
    
    def on_signal_update(self, signal:int, symbol:str):
        self.accept_signal(signal, symbol)
        direction = self.trade_directions(signal)

        ## from portfolio manager 
        portfolio_stats = self.portfolio_manager.get_portfolio_stats_by_symbol(symbol)
        print(f"Portfolio stats: {portfolio_stats}!!!!!!!!!!!!!!!!")

        position = portfolio_stats.get('position')
        current_position_size = position.get('qty', 0.0) if position else 0.0
        unrealized_pnl = portfolio_stats.get('unrealized_pnl', 0.0)
        cash_balance = portfolio_stats.get('cash_balance', 0.0)
        current_price = self.df_orderbook[symbol]['mid_price'].iloc[-1]

        total_portfolio_value = cash_balance + unrealized_pnl
        current_exposure = abs(current_position_size * current_price)
        max_exposure = total_portfolio_value * self.max_exposure_pct
        logger.info(f"{symbol} - Current exposure: {current_exposure:.2f}, Max exposure: {max_exposure:.2f}, Total portfolio value: {total_portfolio_value:.2f}")

        # result from manage position (tp/sl)
        result = self.manage_position(symbol)

        # on new buy signal
        if direction == "BUY":
            logger.info(f"Processing BUY signal for {symbol}")

            # CONDITION 1: if no position exists, buy to enter long position
            if current_position_size == 0.0:
                logger.info(f"No open position for {symbol}, placing new BUY order to enter long position.")
                size = self.calculate_position_size()
                if size:
                    self.current_position_size = size
                    self.entry_position(symbol, direction, size)
                    logger.info(f"Initial position for {symbol} price: {current_price:.4f}")
                else:
                    logger.warning(f"Unable to calculate position size for {symbol}, skipping order placement.")
                    return
                
            # CONDITION 2: if position exists, check exposure and decide whether to scale
            # existing long position
            elif current_position_size > 0.0:
                if result.get("TP/SL hit", True):
                    logger.info(f"Take profit or stop loss hit for {symbol}, closing position.")
                    self.entry_position(symbol, "SELL", current_position_size)
                    return
                # decide whether to scale position
                if current_exposure >= max_exposure:
                    logger.info(f"Max exposure: {max_exposure} reached for {symbol}, ignoring BUY signal.")
                    return
                elif current_exposure < max_exposure:
                    if result.get("TP/SL hit", True):
                        logger.info(f"Take profit or stop loss hit for {symbol}, holding position.")
                        return
                    
                    logger.info(f"Current exposure within threshold. Scaling position for {symbol}.")
                    size = self.calculate_position_size()
                    if size:
                        logger.info(f"Scaling position for {symbol} with additional size: {size:.4f}")
                        self.entry_position(symbol, "BUY", size)

            # existing short position
            elif current_position_size < 0.0:
                if result.get("TP/SL hit", True):
                    logger.info(f"Take profit or stop loss hit for {symbol}, closing short position.")
                    self.entry_position(symbol, "BUY", current_position_size)

        # on new sell signal 
        elif direction == "SELL":
            logger.info(f"Processing SELL signal for {symbol}")

            # CONDITION 1: if no position exists, sell to enter short position
            if current_position_size == 0.0:
                logger.info(f"No open position for {symbol}, placing new SELL order to enter short position.")
                size = self.calculate_position_size()
                if size:
                    self.current_position_size = size
                    self.entry_position(symbol, direction, size)
                    logger.info(f"Initial position for {symbol} price: {current_price:.4f}")
                else:
                    logger.warning(f"Unable to calculate position size for {symbol}, skipping order placement.")
                    return
                
            # CONDITION 2: if position exists, check exposure and decide whether to scale
            # existing short position
            elif current_position_size < 0.0:
                if result.get("TP/SL hit", True):
                    logger.info(f"Take profit or stop loss hit for {symbol}, closing position.")
                    self.entry_position(symbol, "SELL", current_position_size)
                    return
                # decide whether to scale position
                elif current_exposure >= max_exposure:
                    logger.info(f"Max exposure: {max_exposure} reached for {symbol}, ignoring SELL signal.")
                    return
                elif current_exposure < max_exposure:
                    if result.get("TP/SL hit", False):
                        logger.info(f"Take profit or stop loss hit for {symbol}, holding position.")
                        return
                    if size: 
                        logger.info(f"Current exposure within threshold. Scaling position for {symbol}.")
                        self.entry_position(symbol, "SELL", size)

            # existing long position
            elif current_position_size > 0.0:
                if result.get("TP/SL hit", True):
                    logger.info(f"Take profit or stop loss hit for {symbol}, closing long position.")
                    self.entry_position(symbol, "SELL", current_position_size)



    def manage_position(self, symbol:str, atr_multiplier:float=1.0):
        logger.info(f"Managing position for {symbol}.")

        ## from portfolio manager
        portfolio_stats = self.portfolio_manager.get_portfolio_stats_by_symbol(symbol)
        trade_dtls = self.portfolio_manager.on_new_trade()

        entry_price = float(trade_dtls.get('average_price', '0.0')) # filled price
        position = portfolio_stats.get('position')
        current_position_size = position.get('qty', 0.0) if position else 0.0
        unrealized_pnl = portfolio_stats.get('unrealized_pnl', 0.0)

        # current_price = self.df_orderbook[self.symbol]['mid_price'].iloc[-1]
        current_price = self.df_orderbook[symbol]['mid_price'].iloc[-1]

        
        print(f"Entry price: {entry_price}!!!!!!!!!!!!!!!!")
        print(f"Position amount: {current_position_size}!!!!!!!!!!!!!!!!")

        current_atr = float(self.current_atr)

        if current_position_size >0:
            direction = "LONG"
        elif current_position_size < 0:
            direction = "SHORT"
        else:
            direction = "FLAT"

        
        try:
            risk = current_atr * atr_multiplier
            position_value = abs(current_position_size * entry_price)
            pnl_pct = unrealized_pnl / position_value if position_value > 0 else 0.0
            r_multiple = (current_price - entry_price) / risk if direction == "LONG" else (entry_price - current_price) / risk
            logger.info(f"Position metrics for {symbol}: PnL%={pnl_pct:.2%}, R-multiple={r_multiple:.2f}")

            # adjust take profit and stop loss dynamically
            if direction == "LONG":
                if pnl_pct >= 0.02 and r_multiple >= 2.0:  
                    new_sl = entry_price + (0.5 * risk)  # tighter stop loss
                    new_tp = current_price + (1.5 * risk) # higher take profit
                elif pnl_pct >= 0.01 or r_multiple >= 1.5:  
                    new_sl = entry_price + risk
                    new_tp = current_price + (2 * risk)
                else:
                    new_sl = entry_price - risk
                    new_tp = current_price + (2 * risk)
            
            elif direction == "SHORT":
                if pnl_pct >= 0.02 and r_multiple >= 2.0:  
                    new_sl = entry_price - (0.5 * risk)  
                    new_tp = current_price - (1.5 * risk) 
                elif pnl_pct >= 0.01 or r_multiple >= 1.5:  
                    new_sl = entry_price - risk
                    new_tp = current_price - (2 * risk)
                else:
                    new_sl = entry_price + risk
                    new_tp = current_price - (2 * risk)
                    
            logger.info(f"Calculated levels for {symbol}: SL={new_sl:.2f}, TP={new_tp:.2f}")

            tp_sl_hit = False
            if direction == "LONG":
                if current_price >= new_tp:
                    logger.info(f"Take profit hit for {symbol} at price: {current_price:.2f}")
                    tp_sl_hit = True
                elif current_price <= new_sl:
                    logger.info(f"Stop loss hit for {symbol} at price: {current_price:.2f}")
                    tp_sl_hit = True
            elif direction == "SHORT":
                if current_price <= new_tp:
                    logger.info(f"Take profit hit for {symbol} at price: {current_price:.2f}")
                    tp_sl_hit = True
                elif current_price >= new_sl:
                    logger.info(f"Stop loss hit for {symbol} at price: {current_price:.2f}")
                    tp_sl_hit = True

            return {
                "TP/SL hit": tp_sl_hit,
                "new_sl": new_sl,
                "new_tp": new_tp,
                'r_multiple': r_multiple,
                'pnl_pct': pnl_pct,
            }

        except Exception as e:
                logger.error(f"Error managing orders for {symbol}: {e}", exc_info=True)

            
    # total portfolio risk - throttle every 30s in the background
    # here liquidates the position -> need to trigger position
    def drawdown_limit_check(self, symbol) -> bool:
        logger.info(f"Checking drawdown limits for {symbol}.")
        current_price = self.df_orderbook[symbol]['mid_price'].iloc[-1]
        portfolio_stats = self.portfolio_manager.get_portfolio_stats_by_symbol(symbol)
        cash_balance = portfolio_stats.get('cash_balance', 0.0)
        current_position_size = portfolio_stats.get('position', {}).get('qty', 0.0)
        portfolio_value = cash_balance + (current_position_size * current_price)
        if self.peak_value is None:
            self.peak_value = portfolio_value
        if self.initial_value is None:
            self.initial_value = portfolio_value
                
        logger.info(f"Current portfolio value: {portfolio_value}")
        logger.info(f"Initial value: {self.initial_value}")

        self.peak_value = max(self.peak_value, portfolio_value)
        relative_dd = (self.peak_value - portfolio_value) / self.peak_value 
        absolute_dd = (self.initial_value - portfolio_value) / self.initial_value

        if relative_dd >= self.max_relative_drawdown or absolute_dd >= self.max_absolute_drawdown:
            logger.warning(f"Drawdown limits breached. Relative dd: {relative_dd:.2%}, Absolute dd: {absolute_dd:.2%}.")
            self.circuit_breaker.force_open(f"Drawdown limit breached for {symbol}.")
            return True, relative_dd, absolute_dd
        return False, relative_dd, absolute_dd


    

            



        


        



        




    

    






    

