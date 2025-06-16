import numpy as np 
import pandas as pd
from app.utils.logger import setup_logger
from app.utils.config import settings
from app.utils.logger import main_logger as logger
from binance.client import Client
from app.portfolio.portfolio_manager import PortfolioManager
from app.strategy.macd_strategy import MACDStrategy
from app.api.binance_gateway import BinanceGateway
from app.api.binance_api import BinanceApi
from app.services.circuit_breaker import RedisCircuitBreaker

#TODO: explain thought process on take profit/ stop loss - should we sell everything? or pause trading
#TODO: listen to depth order book and take the mid price from best bid and ask
#TODO : dynamic take profit and stop loss - adjust take profit and stop loss pct based on market vol (multiples of ATR)
#TODO : handle market order (default) and limit order (fill up price)
#TODO : call binance to creater order if receive buy signal - how much to buy?

class RiskManager:
    def __init__(self, 
                 symbols: list[str],
                 api:BinanceApi,
                 portfolio_manager:PortfolioManager,
                 circuit_breaker: RedisCircuitBreaker,
                 max_risk_per_trade_pct:float = settings.MAX_RISK_PER_TRADE_PCT, 
                 max_absolute_drawdown:float = settings.MAX_ABSOLUTE_DRAWDOWN,
                 max_relative_drawdown:float = settings.MAX_RELATIVE_DRAWDOWN, 
                 max_exposure_pct:float = settings.MAX_EXPOSURE_PCT
                 ):
        self.api = api
        self.symbols = symbols
        self.active_trades = {symbol:{} for symbol in symbols}
        self.orderbook_df = {symbol:pd.DataFrame() for symbol in symbols}
        self.candlestick_df = {symbol:pd.DataFrame() for symbol in symbols}
        self.portfolio_manager = portfolio_manager
        self.circuit_breaker = circuit_breaker
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_absolute_drawdown = max_absolute_drawdown
        self.max_relative_drawdown = max_relative_drawdown
        self.max_exposure_pct = max_exposure_pct
        

    def data_aggregator(self, data:dict):
        logger.info("Fetching orderbook data..")
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

    # store rolling historical candlestick data as df 
    def process_candlestick(self, data: dict):
        logger.info("Processing candlestick data..")
        logger.debug(f"Received candlestick data: {data}")
        
        if not data.get('is_closed', False):
            logger.debug("Received incomplete candlestick. Skipping.")
            return

        try:
            row = pd.DataFrame([{
                'timestamp': data['start_time'],
                'open': float(data['open']),
                'high': float(data['high']),
                'low': float(data['low']),
                'close': float(data['close']),
                'volume': float(data['volume']),
                'is_closed': data['is_closed']
            }])
            row['timestamp'] = pd.to_datetime(row['timestamp'], unit='ms')
            row.set_index('timestamp', inplace=True)
            
            if self.candlestick_df.empty:
                self.candlestick_df = row
                logger.info(f"Initialized candlestick dataframe with first row: {row}")
            else: 
                timestamp = row.index[0]
                if timestamp not in self.candlestick_df.index:
                    self.candlestick_df = pd.concat([self.candlestick_df, row])
                    self.candlestick_df = self.candlestick_df.tail(500)  # Keep last 500 candles
                    logger.info(f"Added new candlestick at {timestamp}")
                else:
                    self.candlestick_df.loc[timestamp] = row.iloc[0]
                    logger.info(f"Updated existing candlestick at {timestamp}")
        except Exception as e:
            logger.error(f"Error processing candlestick data: {e}", exc_info=True)

    # average true range - measure price vol of asset approx 14 days 
    def calculate_atr(self, period=14):
        if self.candlestick_df.empty:
            logger.warning("No candlestick data available for ATR calculations.")
            return None 
        
        try:
            close = self.candlestick_df['close']
            high = self.candlestick_df['high']
            low = self.candlestick_df['low']
            prev_close = close.shift(1)
            high_low = high - low
            high_close = abs(high - prev_close)
            low_close = abs(low - prev_close)
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

            atr = true_range.rolling(window=period, min_periods=1).mean()
            return float(atr.iloc[-1]) if not atr.empty else None
        except Exception as e:
            logger.error(f"Error calculating ATR: {e}", exc_info=True)
            return None

    # dynamic position size 
    # should be based on current existing positions - net positions? 
    def calculate_position_size(self) -> float:
        atr = self.calculate_atr()
        if atr is None or atr <= 0:
            logger.warning("Unable to calculate ATR. Skipping position sizing and trade.")
            return 
        
        entry_price = self.orderbook_df['mid_price'].iloc[-1] 
        risk_amount = entry_price * self.max_risk_per_trade_pct
        position_size = risk_amount / atr
        return position_size
    
    def trade_directions(self, signal:int) -> str:
        if signal == settings.SIGNAL_SCORE_BUY:
            return "BUY"
        elif signal == settings.SIGNAL_SCORE_SELL:
            return "SELL"
        return "HOLD"
    
    def accept_signal(self, signal: int, symbol:str) -> str:
        direction = self.trade_directions(signal)
        portfolio_stats = self.portfolio_manager.get_portfolio_stats(symbol)
        portfolio_value = self.portfolio_manager.get_total_portfolio_value()
        max_exposure = portfolio_value * self.max_exposure_pct
        position = portfolio_stats['position']
        current_price = self.orderbook_df[symbol]['mid_price'].iloc[-1]
        net_exposure = abs(position['qty'] * current_price)

        if not direction or direction == "HOLD":
            logger.info("No valid trade signal received. Holding position.")
            return None
        
        if direction == "BUY":
            if net_exposure >= max_exposure:
                logger.info(f"Max exposure reached for {symbol}, ignoring signal.")
                return None
            elif net_exposure < max_exposure:
                logger.info(f"Accepting BUY signal for {symbol}. Current exposure: {net_exposure}.")
                return direction
        elif direction == "SELL":
            logger.info(f"Accepted signal for {symbol}: {direction}.")
            return direction

    # check exposure- see if wanna buy more ?
    def entry_position(self, symbol: str):
        portfolio_stats = self.portfolio_manager.get_portfolio_stats(symbol)
        # if no existing position, calculate position size
        if portfolio_stats['position'] is None or portfolio_stats['position']['qty'] == 0:
            logger.info(f"No open position for {symbol}, calculating position size.")
            position_size = self.calculate_position_size(symbol)
            if not position_size:
                logger.warning(f"Could not calculate position size for {symbol}. Skipping trade.")
                return 
            
            try:
                # default to market order
                entry_price = self.orderbook_df[symbol]['mid_price'].iloc[-1]
                direction = self.accept_signal()
                self.api.place_market_order(
                    symbol=symbol,
                    side="BUY",
                    type="MARKET",
                    qty=position_size,
                )
                logger.info(f"Placed market order for {symbol} with quantity: {position_size}")

                self.active_trades[symbol] = {
                    "entry_price": entry_price,
                    "quantity": position_size,
                    "trade_direction": self.trade_directions(direction)
                }
            except Exception as e:
                logger.error(f"Failed to place market order for {symbol}: {e}")
                return

    def manage_position(self, atr_multiplier=1.0, symbol: str):
        portfolio_stats = self.portfolio_manager.get_portfolio_stats(symbol)
        position = portfolio_stats['position']
        entry_price = position['average_price']
        qty = position['qty']
        direction = "LONG" if qty>0 else "SHORT"

        atr = self.calculate_atr()
        risk = atr * atr_multiplier
        current_price = self.orderbook_df['mid_price'].iloc[-1]
        # risk reward ratio 
        r_multiple = (current_price - entry_price) / risk if direction == "LONG" else (entry_price - current_price) / risk

        ## take profit and stop loss orders
        # return multiple - risk management strategy 
        # track tp/sl 
        new_tp = None
        new_sl = None

        if direction == "LONG":
            if r_multiple >= 2.0:
                new_sl = entry_price + risk 
                new_tp = current_price + (2 * risk)
            elif r_multiple >= 1.0:
                new_sl = entry_price + (3 * risk)
                new_tp = current_price + risk
        
        elif direction == "SHORT":
            if r_multiple >= 2.0:
                new_sl = entry_price - risk 
                new_tp = current_price - (2 * risk)
            elif r_multiple >= 1.0:
                new_sl = entry_price - (3 * risk)
                new_tp = current_price - risk
                
        try:
            # existing open orders
            open_orders = self.api.get_open_orders(symbol=symbol)

            update_order = False # default
            current_tp = None 
            current_sl = None

            for order in open_orders:
                if direction == "LONG":
                    if order['type'] == 'STOP_MARKET' and order['side'] == 'SELL':
                        current_sl = float(order['stopPrice'])
                    elif order['type'] == 'TAKE_PROFIT_MARKET' and order['side'] == 'SELL':
                        current_tp = float(order['stopPrice'])
                elif direction == "SHORT":
                    if order['type'] == 'STOP_MARKET' and order['side'] == 'BUY':
                        current_sl = float(order['stopPrice'])
                    elif order['type'] == 'TAKE_PROFIT_MARKET' and order['side'] == 'BUY':
                        current_tp = float(order['stopPrice'])

            # cancel tp if sl is filled (vice versa)
            if current_sl is None and new_tp is not None:
                self.api.cancel_order(symbol=symbol)
                logger.info(f"Take profit filled for {symbol}, cancelling stop loss order.")
                return
            if current_tp is None and new_sl is not None:
                self.api.cancel_order(symbol=symbol)
                logger.info(f"Stop loss filled for {symbol}, cancelling take profit order.")
                return

            # check diff to see if we need to update orders
            if abs(current_sl - new_sl) > 0.01 or abs(current_tp - new_tp) > 0.01:
                update_order = True
                logger.info(f"Updating stop loss and take profit orders for {symbol}.")

            if update_order:
                # cancel existing orders
                self.api.cancel_open_orders(symbol=symbol)
                logger.info(f"Cancelled existing orders for {symbol}.")
                
                # place new stop loss and take profit orders
                self.api.place_stop_loss(
                    side=direction,
                    type="STOP_LOSS",
                    qty=qty, # sell everything?
                    symbol=symbol,
                    price=new_sl, 
                    tif=settings.TIME_IN_FORCE_GTC
                )
                logger.info(f"Placed stop loss order for {symbol} at price: {new_sl}")
                
                self.api.place_take_profit_order(
                    side=direction,
                    type="TAKE_PROFIT",
                    qty=qty,
                    symbol=symbol,
                    price=new_tp,
                    tif=settings.TIME_IN_FORCE_GTC
                )
                logger.info(f"Placed take profit order for {symbol} at price: {new_tp}")
            
        except Exception as e:
            logger.error(f"Error managing position for {symbol}: {e}", exc_info=True)

            
    ## total portfolio risk
    def calculate_drawdown_limits(self) -> bool:
        portfolio_value = self.portfolio_manager.get_total_portfolio_value()
        if self.candlestick_df.empty:
            logger.warning("No candlestick data available for drawdown calculations.")
            return True
        peak_value = self.candlestick_df['high'].max() 
        trough_value = self.candlestick_df['low'].min()
        # init portfolio at the start of session
        self.current_value = portfolio_value

        relative_dd = (peak_value - portfolio_value)/ peak_value
        absolute_dd = (portfolio_value - self.current_value)/ self.current_value
        
        if relative_dd > self.max_relative_drawdown or absolute_dd > self.max_absolute_drawdown:
            logger.warning(f"Drawdown limits breached.")
            self.circuit_breaker.force_open(f"Drawdown limit breached. Relative dd: {relative_dd:.2%}, Absolute dd: {absolute_dd:.2%}.")
            for symbol, position in PortfolioManager.get_positions.items():
                qty = position['qty']
                try:
                    # liquidate position
                    self.api.place_market_order(
                        side="SELL",
                        type="MARKET",
                        qty=qty,
                        symbol=symbol
                    )
                    logger.info(f"Liquidated position for {symbol}:{qty} units.")
                except Exception as e:
                    logger.error(f"Unable to liquidate position for {symbol}: {e}.")
            return False
        return True 
        

    

            



        


        



        




    

    






    

