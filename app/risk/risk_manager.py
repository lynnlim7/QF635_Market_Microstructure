import numpy as np 
import pandas as pd
from binance import Client
from app.utils.config import settings
from app.utils.logger import main_logger as logger
from app.portfolio.portfolio_manager import PortfolioManager
from app.api.binance_api import BinanceApi
from app.services.circuit_breaker import RedisCircuitBreaker

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


    def on_new_orderbook(self, data:dict):
        if not isinstance(data, dict):
            logger.warning(f"Invalid data format for orderbook: {data}")
            return
            
        logger.info("Processing orderbook data.")

        timestamp = pd.to_datetime(data.get("timestamp", None), unit='ms')
        symbol = data.get('contract_name', self.symbol).upper()  

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
        else:
            self.df_orderbook[symbol] = pd.concat([self.df_orderbook[symbol], row]).tail(500)

        self.calculate_position_size()
        # self.manage_position(symbol)
           
    def on_new_candlestick(self, data):
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
        logger.info(f"Received signal from queue: {signal}")
    
    def on_signal_update(self, signal:int, symbol:str):
        logger.info(f"=====SIGNAL UPDATE=====: {signal} for {symbol}")

        self.accept_signal(signal, symbol)
        direction = self.trade_directions(signal)

        # portfolio_stats = self.portfolio_manager.get_portfolio_stats_by_symbol(symbol)

        # workaround using api 
        portfolio_stats = self.api.get_current_position()
        print(f"portfolio_stats:{portfolio_stats}!!!!!!!!!!!!!!!!!!!!")
        
        position_amounts = [float(p.get('positionAmt', 0.0)) for p in portfolio_stats if p.get('positionAmt')]
        unrealized_pnls = [float(p.get('unRealizedProfit', 0.0)) for p in portfolio_stats if p.get('positionAmt')]

        position_amt = position_amounts[0] if position_amounts else 0.0
        unrealized_pnl = unrealized_pnls[0] if unrealized_pnls else 0.0
    
        # position = portfolio_stats.get('position')
        # unrealized_pnl = portfolio_stats.get('unrealized_pnl', 0.0)

        current_price = self.df_orderbook[symbol]['mid_price'].iloc[-1]

        if direction == "BUY":
            logger.info(f"Processing BUY signal for {symbol} with current price: {current_price:.4f}")
            # if position exists, check if we can buy more
            # if position and position.get('qty') != 0:
            if len(position_amounts)>0:
                futures_balance = self.api.get_account_balance()
                balance = 0.0
                for asset in futures_balance:
                    if asset.get('asset') == 'USDT':
                        balance = float(asset.get('balance', 0.0))
                        break
                total_portfolio_value = balance + unrealized_pnl
                # current_exposure = abs(position['qty'] * current_price)
                current_exposure = abs(position_amounts[0]['positionAmt'] * current_price)
                max_exposure = total_portfolio_value * self.max_exposure_pct
                logger.info(f"Total portfolio value: {total_portfolio_value}, Current exposure: {current_exposure}, Max exposure: {max_exposure}")
                # if current exposure exceeds threshold, we cannot buy more 
                if current_exposure >= max_exposure:
                    logger.info(f"Max exposure: {max_exposure} reached for {symbol}, ignoring BUY signal.")
                else:
                    logger.info(f"Current exposure within threshold. Accepting BUY signal for {symbol}.")
                    self.entry_position(symbol, direction)
            else: 
                # no position exists, we can buy
                logger.info(f"No open position for {symbol}, accepting BUY signal.")
                self.entry_position(symbol, direction)
        elif direction == "SELL":
            # if no position exists, we cannot sell 
            # if not position or position.get('qty') == 0:
            if not position_amounts or position_amt == 0.0:
                logger.info(f"No open position for {symbol}, cannot accept SELL signal.")
            else:
                logger.info(f"Accepted SELL signal for {symbol}.")
                self.entry_position(symbol, direction)
        else:
            # if direction is HOLD or invalid
            logger.info(f"Invalid signal direction: {direction} for {symbol}. Holding position.")
            return

    def entry_position(self, symbol: str, direction: str = None):
        # entry_price = self.df_orderbook[symbol]['mid_price'].iloc[-1]
        try:
            self.api.place_market_order(
            symbol=symbol,
            side=direction,
            qty=self.current_position_size,
            )
            logger.info(f"Placed market order for {symbol} with quantity: {self.current_position_size:.3f}")
        except Exception as e:
            logger.error(f"Failed to place market order for {symbol}: {e}")
            return None

 

    # def manage_position(self, symbol: str, atr_multiplier=1.0):
    #     portfolio_stats = self.portfolio_manager.get_portfolio_stats_by_symbol(symbol)
    #     position = portfolio_stats['position']
        
    #     if position is None or position['qty'] == 0:
    #         logger.info(f"No open position for {symbol} to manage.")
    #         return
            
    #     try:
    #         entry_price = position['average_price']
    #         qty = position['qty']
    #         direction = "LONG" if qty > 0 else "SHORT"
    #         unrealized_pnl = portfolio_stats['unrealized_pnl'] or 0.0

    #         atr = self.current_atr
    #         if atr is None:
    #             logger.warning(f"Could not calculate ATR for {symbol}. Skipping position management.")
    #             return
                
    #         risk = atr * atr_multiplier
            
    #         # Fix orderbook data access
    #         if symbol not in self.df_orderbook or self.df_orderbook[symbol].empty:
    #             logger.warning(f"No orderbook data available for {symbol}")
    #             return
                
    #         current_price = self.df_orderbook[symbol]['mid_price'].iloc[-1]
            
    #         # Calculate both PnL percentage and R-multiple
    #         position_value = abs(qty * current_price)
    #         pnl_pct = unrealized_pnl / position_value if position_value > 0 else 0
    #         r_multiple = (current_price - entry_price) / risk if direction == "LONG" else (entry_price - current_price) / risk
            
    #         logger.info(f"Position metrics for {symbol}: PnL%={pnl_pct:.2%}, R-multiple={r_multiple:.2f}")
            
    #         # adjust take profit and stop loss 
    #         if direction == "LONG":
    #             if pnl_pct >= 0.02 and r_multiple >= 2.0:  
    #                 new_sl = entry_price + (0.5 * risk)  # tighter stop loss
    #                 new_tp = current_price + (1.5 * risk) # higher take profit
    #             elif pnl_pct >= 0.01 or r_multiple >= 1.5:  
    #                 new_sl = entry_price + risk
    #                 new_tp = current_price + (2 * risk)
    #             else:
    #                 new_sl = entry_price - risk
    #                 new_tp = current_price + (2 * risk)
            
    #         elif direction == "SHORT":
    #             if pnl_pct >= 0.02 and r_multiple >= 2.0:  
    #                 new_sl = entry_price - (0.5 * risk)  
    #                 new_tp = current_price - (1.5 * risk) 
    #             elif pnl_pct >= 0.01 or r_multiple >= 1.5:  
    #                 new_sl = entry_price - risk
    #                 new_tp = current_price - (2 * risk)
    #             else:
    #                 new_sl = entry_price + risk
    #                 new_tp = current_price - (2 * risk)
                    
    #         logger.info(f"Calculated levels for {symbol}: SL={new_sl:.2f}, TP={new_tp:.2f}")
                    
    #         try:
    #             # existing open orders
    #             open_orders = self.api.get_open_orders()
    #             logger.info(f"Current open orders: {open_orders}")
    #             if open_orders is None:
    #                 logger.warning(f"No open orders found for {symbol}.")
    #                 return

    #             update_order = False # default
    #             current_tp = None 
    #             current_sl = None

    #             for order in open_orders:
    #                 if direction == "LONG":
    #                     if order['type'] == 'STOP_MARKET' and order['side'] == 'SELL':
    #                         current_sl = float(order['stopPrice'])
    #                     elif order['type'] == 'TAKE_PROFIT_MARKET' and order['side'] == 'SELL':
    #                         current_tp = float(order['stopPrice'])
    #                 elif direction == "SHORT":
    #                     if order['type'] == 'STOP_MARKET' and order['side'] == 'BUY':
    #                         current_sl = float(order['stopPrice'])
    #                     elif order['type'] == 'TAKE_PROFIT_MARKET' and order['side'] == 'BUY':
    #                         current_tp = float(order['stopPrice'])

    #                 # cancel tp if sl is filled (vice versa)
    #                 if current_sl is None and new_tp is not None:
    #                     self.api.cancel_order(symbol=symbol, order_id=order['orderId'])
    #                     logger.info(f"Take profit filled for {symbol}, cancelling stop loss order.")
    #                     return
    #                 if current_tp is None and new_sl is not None:
    #                     self.api.cancel_order(symbol=symbol, order_id=order['orderId'])
    #                     logger.info(f"Stop loss filled for {symbol}, cancelling take profit order.")
    #                     return

    #             # check diff to see if we need to update orders
    #             if abs(current_sl - new_sl) > 0.01 or abs(current_tp - new_tp) > 0.01:
    #                 update_order = True
    #                 logger.info(f"Updating stop loss and take profit orders for {symbol}.")

    #             if update_order:
    #                 # cancel existing orders
    #                 self.api.cancel_open_orders(symbol=symbol)
    #                 logger.info(f"Cancelled existing orders for {symbol}.")

    #                 # TODO: these apis dont have some of the arguments, check again
    #                 # place new stop loss and take profit orders
    #                 logger.info(f"Placing stop loss order for {symbol} at price: {new_sl}")
    #                 self.api.place_stop_loss(
    #                     quantity=qty,
    #                     price=new_sl
    #                 )
                    
    #                 logger.info(f"Placing take profit order for {symbol} at price: {new_tp}")
    #                 self.api.place_take_profit(
    #                     quantity=qty,
    #                     price=new_tp
    #                 )
                
    #         except Exception as e:
    #             logger.error(f"Error managing orders for {symbol}: {e}", exc_info=True)
    #     except Exception as e:
    #         logger.error(f"Error managing position for {symbol}: {e}", exc_info=True)

            
    # ## total portfolio risk
    # # here liquidates the position -> need to trigger position
    # def calculate_drawdown_limits(self, symbol) -> bool:
    #     portfolio_stats = self.portfolio_manager.get_portfolio_stats_by_symbol(symbol)
    #     portfolio_value = portfolio_stats['total_pnl'] if portfolio_stats else 0.0
        
    #     if symbol not in self.df_candlestick or self.df_candlestick[symbol].empty:
    #         logger.warning(f"No candlestick data available for {symbol} for drawdown calculations.")
    #         return True
            
    #     try:
    #         df_candlestick = self.df_candlestick[symbol]
    #         peak_value = df_candlestick['high'].max() 
    #         trough_value = df_candlestick['low'].min()
            
    #         if self.current_value == 0.0:
    #             self.current_value = portfolio_value
    #             return True
                
    #         logger.info(f"Current portfolio value: {portfolio_value}")
    #         logger.info(f"Current value: {self.current_value}")
    #         logger.info(f"Peak value from candlesticks: {peak_value}")
    #         logger.info(f"Trough value from candlesticks: {trough_value}")

    #         relative_dd = (peak_value - portfolio_value) / peak_value if peak_value > 0 else 0
    #         absolute_dd = (portfolio_value - self.current_value) / self.current_value if self.current_value > 0 else 0

            
    #         if relative_dd > self.max_relative_drawdown or absolute_dd > self.max_absolute_drawdown:
    #             logger.warning(f"Drawdown limits breached. Relative dd: {relative_dd:.2%}, Absolute dd: {absolute_dd:.2%}.")

    #             for symbol, position in self.portfolio_manager.get_positions().items():
    #                 qty = position['qty']
    #                 try:
    #                     if qty > 0:
    #                         logger.info(f"Liquidating long position for {symbol}:{qty} units.")
    #                         # liquidate position
    #                         self.api.place_market_order(
    #                             side="SELL",
    #                             qty=qty,
    #                             symbol=symbol
    #                         )
    #                     logger.info(f"Liquidated position for {symbol}:{qty} units.")
    #                     self.circuit_breaker.force_open(f"Drawdown limit breached.")
    #                 except Exception as e:
    #                     logger.error(f"Unable to liquidate position for {symbol}: {e}.")
    #             return False
    #         return True
    #     except Exception as e:
    #         logger.error(f"Error calculating drawdown limits: {e}", exc_info=True)
    #         return True  
        

    

            



        


        



        




    

    






    

