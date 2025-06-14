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
#TODO : handle market order (default) and limit order (fill up price)
#TODO : call binance to creater order if receive buy signal - how much to buy?


risk_logger = setup_logger(
            logger_name="risk",
            logger_path="./logs/risk",
            log_type="risk",
            enable_console=False
            )

class RiskManager:
    def __init__(self, 
                 symbol: str,
                 api:BinanceApi,
                 circuit_breaker: RedisCircuitBreaker,
                 max_risk_per_trade_pct:float = settings.MAX_RISK_PER_TRADE_PCT, 
                 max_absolute_drawdown:float = settings.MAX_ABSOLUTE_DRAWDOWN,
                 max_relative_drawdown:float = settings.MAX_RELATIVE_DRAWDOWN, 
                 ):
        self.api = api
        self.symbol = symbol
        self.active_trades = {}  
        self.orderbook_df = pd.DataFrame()
        self.candlestick_df = pd.DataFrame()
        self.circuit_breaker = circuit_breaker
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_absolute_drawdown = max_absolute_drawdown
        self.max_relative_drawdown = max_relative_drawdown
        

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

    # store rolling historical candlestick data as df 
    def process_candlestick(self, data: dict):
        risk_logger.info("Processing candlestick data..")
        risk_logger.debug(f"Received candlestick data: {data}")
        
        if not data.get('is_closed', False):
            risk_logger.debug("Received incomplete candlestick. Skipping.")
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
                risk_logger.info(f"Initialized candlestick dataframe with first row: {row}")
            else: 
                timestamp = row.index[0]
                if timestamp not in self.candlestick_df.index:
                    self.candlestick_df = pd.concat([self.candlestick_df, row])
                    self.candlestick_df = self.candlestick_df.tail(500)  # Keep last 500 candles
                    risk_logger.info(f"Added new candlestick at {timestamp}")
                else:
                    self.candlestick_df.loc[timestamp] = row.iloc[0]
                    risk_logger.info(f"Updated existing candlestick at {timestamp}")
        except Exception as e:
            risk_logger.error(f"Error processing candlestick data: {e}", exc_info=True)

    # average true range - measure price vol of asset approx 14 days 
    def calculate_atr(self, period=14):
        if self.candlestick_df.empty:
            risk_logger.warning("No candlestick data available for ATR calculations.")
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
            risk_logger.error(f"Error calculating ATR: {e}", exc_info=True)
            return None

    # dynamic position size 
    # should be based on current existing positions - net positions? 
    def calculate_position_size(self) -> float:
        atr = self.calculate_atr()
        if atr is None or atr <= 0:
            risk_logger.warning("Unable to calculate ATR. Skipping position sizing and trade.")
            return 
        
        entry_price = self.orderbook_df['mid_price'].iloc[-1] 
        risk_amount = entry_price * self.max_risk_per_trade_pct
        position_size = risk_amount / atr
        return position_size
    
    # check if position is open
    def is_position_open(self, positions:list) -> bool:
        for pos in positions:
            if pos['symbol'] == self.symbol and float(pos['positionAmt']) != 0.0:
                risk_logger.info(f"Position for {self.symbol} is open with quantity: {pos['positionAmt']}")
                return True
        return False
        
    # callback function from strategy - takes signal from queue
    def accept_signal(self, signal: int):
        positions = Client.futures_position_information()
        if not self.is_position_open(positions):
            main_logger.info(f"Received Signal from strategy: {signal}")
        else:
            main_logger.info(f"Position already open for {self.symbol}, ignoring signal: {signal}")
            return
    
    # check exposure- see if wanna buy more 
    def entry_position(self):
        if self.is_position_open() is False: #FIX ME
            position_size = self.calculate_position_size()
            try:
                # default to market order
                entry_price = self.orderbook_df['mid_price'].iloc[-1]
                direction = self.accept_signal()
                self.api.place_market_order(
                    side=direction,
                    qty=position_size,
                    symbol=self.symbol
                )
                risk_logger.info(f"Placed market order for {self.symbol} with quantity: {position_size}")

                # # backup limit order at entry price 
                # self.api.place_limit_order(
                #     side=direction,
                #     qty=position_size,
                #     symbol=self.symbol,
                #     price=entry_price, 
                #     tif=settings.TIME_IN_FORCE_GTC
                # )
                risk_logger.info(f"Placed limit order for {self.symbol} at price: {entry_price}")

                self.active_trades[self.symbol] = {
                    "entry_price": entry_price,
                    "quantity": position_size,
                    "trade_direction": self.trade_directions(direction)
                }
                
            except Exception as e:
                risk_logger.error(f"Failed to place market order for {self.symbol}: {e}")

    def manage_position(self, atr_multiplier=1.0):
        positions = self.api.futures_position_information()
        if positions is None or positions == 0:
            risk_logger.info(f"No open positions.")
            return 
        
        entry_price = float(positions['entryPrice'])
        qty = float(positions['positionAmt'])
        direction = positions['positionSide'] == 'LONG' if positions > 0 else "SHORT"

        atr = self.calculate_atr()
        risk = atr * atr_multiplier
        current_price = self.orderbook_df['mid_price'].iloc[-1]
        # risk reward ratio 
        r_multiple = (current_price - entry_price) / risk if direction == "LONG" else (entry_price - current_price) / risk
            
        # cancel old stop loss and take profit orders and create new ones
        self.api.futures_cancel_all_open_orders(symbol=self.symbol)

        ## take profit and stop loss orders
        # Return multiple - risk management strategy 
        if direction == "LONG":
            if r_multiple >= 2.0:
                sl = entry_price + risk 
                tp = current_price + (2 * risk)
            elif r_multiple >= 1.0:
                sl = entry_price + (3 * risk)
                tp = current_price + risk
        
        elif direction == "SHORT":
            if r_multiple >= 2.0:
                sl = entry_price - risk 
                tp = current_price - (2 * risk)
            elif r_multiple >= 1.0:
                sl = entry_price - (3 * risk)
                tp = current_price - risk

        

        # place new stop loss and take profit orders
        self.api.place_stop_loss_order(
            side=direction,
            qty=qty,
            symbol=self.symbol,
            stop_price=sl,
            price=sl,  # price for stop loss order
            tif=settings.TIME_IN_FORCE_GTC
        )
        risk_logger.info(f"Placed stop loss order for {self.symbol} at price: {sl}")
        self.api.place_take_profit_order(
            side=direction,
            qty=qty,
            symbol=self.symbol,
            stop_price=tp,
            price=tp,  # price for take profit order
            tif=settings.TIME_IN_FORCE_GTC
        )
        risk_logger.info(f"Placed take profit order for {self.symbol} at price: {tp}")
            
    ## total portfolio risk
    def calculate_drawdown_limits(self) -> bool:
        peak_value = self.candlestick_df['high'].max() 
        current_value = 


        if self.initial_value is None:
            self.initial_value = current_value 
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
                    self.api.place_market_order(
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
    
    

            



        


        



        




    

    






    

