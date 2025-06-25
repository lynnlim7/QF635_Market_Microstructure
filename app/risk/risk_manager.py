import pandas as pd

from app.api.base_api import BaseApi
from app.portfolio.portfolio_manager import PortfolioManager
from app.services.circuit_breaker import RedisCircuitBreaker
from app.utils.config import settings
from app.utils.logger import main_logger as logger


#TODO: explain thought process on take profit/ stop loss - should we sell everything? or pause trading
#TODO: listen to depth order book and take the mid price from best bid and ask
#TODO : dynamic take profit and stop loss - adjust take profit and stop loss pct based on market vol (multiples of ATR)
#TODO : handle market order (default) and limit order (fill up price)
#TODO : call binance to creater order if receive buy signal - how much to buy?

class RiskManager:
    def __init__(self,
                 symbol: str,
                 api:BaseApi,
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
        self.emergency_shutdown = False
        self.peak_value = None
        self.initial_value = None
        self.real_data_initialized = False

    def on_new_orderbook(self, data:dict):
        if not isinstance(data, dict):
            logger.warning(f"Invalid data format for orderbook: {data}")
            return


        timestamp = pd.to_datetime(data.get("timestamp", None), unit='ms')
        symbol = data.get('contract_name', self.symbol).upper()
        # logger.info(f"Processing orderbook for symbol: {symbol}")


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
            # logger.info(f"Created new orderbook entry for symbol: {symbol}")
        else:
            self.df_orderbook[symbol] = pd.concat([self.df_orderbook[symbol], row]).tail(500)
            # logger.info(f"Updated orderbook for symbol: {symbol}")

        self.calculate_position_size()
        # self.manage_position(symbol)

    def on_new_candlestick(self, data):
        logger.info("Processing new candlestick data.")
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
            # logger.info(f"Calculated position size: {position_size:.4f} with entry price: {entry_price:.4f} and ATR: {self.current_atr:.4f}")
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

    def get_closing_direction(self, current_position_size: float) -> str:
        if current_position_size > 0:
            return "SELL"
        elif current_position_size < 0:
            return "BUY"
        else:
            return None

    def entry_position(self, symbol: str, size: float, direction: str = None):
        try:
            logger.info(f"Trying to place market order in api: {symbol} , side: {direction}, qty: {size}")
            self.api.place_market_order(
            symbol=symbol,
            side=direction,
            qty=float(size),
            )
        except Exception as e:
            logger.error(f"Failed to place market order for {symbol}: {e}")
            return None

    def on_signal_update(self, signal:int, symbol:str):
        # Check for emergency shutdown first
        if self.emergency_shutdown:
            logger.warning(f"EMERGENCY SHUTDOWN ACTIVE: Ignoring signal {signal} for {symbol}")
            return

        # Check circuit breaker status
        if self.check_circuit_breaker_status():
            logger.warning(f"Circuit breaker is OPEN: Ignoring signal {signal} for {symbol}")
            return

        self.accept_signal(signal, symbol)
        direction = self.trade_directions(signal)

        # symbol = symbol.upper()

        ## from portfolio manager
        portfolio_stats = self.portfolio_manager.get_portfolio_stats_by_symbol(symbol)
        print(f"Portfolio stats: {portfolio_stats}!!!!!!!!!!!!!!!!")

        position = portfolio_stats.get('position')
        current_position_size = round(position.get('qty', 0.0) if position else 0.0, 8)
        unrealized_pnl = portfolio_stats.get('unrealized_pnl', 0.0) if position else 0.0
        cash_balance = portfolio_stats.get('cash_balance', 0.0)

        logger.info(f"Current position size for {symbol}: {current_position_size}")

        if symbol not in self.df_orderbook or self.df_orderbook[symbol].empty:
            logger.warning(f"No orderbook data available for {symbol}. Available symbols: {list(self.df_orderbook.keys())}")
            return
        
        current_price = self.df_orderbook[symbol]['mid_price'].iloc[-1]

        total_portfolio_value = cash_balance + unrealized_pnl
        current_exposure = abs(current_position_size * current_price)
        max_exposure = total_portfolio_value * self.max_exposure_pct
        logger.info(f"{symbol} - Current exposure: {current_exposure:.2f}, Max exposure: {max_exposure:.2f}, Total portfolio value: {total_portfolio_value:.2f}")

        # result from manage position (tp/sl)
        result = self.manage_position(symbol)

        # TODO: think of how to handle this
        # set threshold to deal with error in case of extremely small position size
        position_size_threshold = 1e-10

        if abs(current_position_size) < position_size_threshold:
            current_position_size = 0.0

        # on new buy signal
        if direction == "BUY":
            logger.info(f"Processing BUY signal for {symbol}")

            # CONDITION 1: if no position exists, buy to enter long position
            if current_position_size == 0.0:
                logger.info(f"No open position for {symbol}, placing new BUY order to enter long position.")
                size = self.calculate_position_size()
                print(f"Size: {size}!!!!!!!!!!!!!!!!!!!!!!!!")
                if size:
                    self.current_position_size = size
                    self.entry_position(symbol, size, direction)
                    logger.info(f"Initial position for {symbol} price: {current_price:.4f}")
                else:
                    logger.warning(f"Unable to calculate position size for {symbol}, skipping order placement.")
                    return

            # CONDITION 2: if position exists, check exposure and decide whether to scale
            # existing long position
            elif current_position_size > 0.0:
                if result.get("TP/SL hit", True):
                    logger.info(f"Take profit or stop loss hit for {symbol}, closing position.")
                    closing_direction = self.get_closing_direction(current_position_size)
                    self.entry_position(symbol, current_position_size, closing_direction)
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
                        self.entry_position(symbol, size, direction)

            # existing short position
            elif current_position_size < 0.0:
                if result.get("TP/SL hit", True):
                    logger.info(f"Take profit or stop loss hit for {symbol}, closing short position.")
                    closing_direction = self.get_closing_direction(current_position_size)
                    self.entry_position(symbol, abs(current_position_size), closing_direction)

        # on new sell signal
        elif direction == "SELL":
            logger.info(f"Processing SELL signal for {symbol}")

            # CONDITION 1: if no position exists, sell to enter short position
            if current_position_size == 0.0:
                logger.info(f"No open position for {symbol}, placing new SELL order to enter short position.")
                size = self.calculate_position_size()
                if size:
                    self.current_position_size = size
                    self.entry_position(symbol, size, direction)
                    logger.info(f"Initial position for {symbol} price: {current_price:.4f}")
                else:
                    logger.warning(f"Unable to calculate position size for {symbol}, skipping order placement.")
                    return

            # CONDITION 2: if position exists, check exposure and decide whether to scale
            # existing short position
            elif current_position_size < 0.0:
                if result.get("TP/SL hit", True):
                    logger.info(f"Take profit or stop loss hit for {symbol}, closing position.")
                    closing_direction = self.get_closing_direction(current_position_size)
                    self.entry_position(symbol, abs(current_position_size), closing_direction)
                    return
                # decide whether to scale position
                elif current_exposure >= max_exposure:
                    logger.info(f"Max exposure: {max_exposure} reached for {symbol}, ignoring SELL signal.")
                    return
                elif current_exposure < max_exposure:
                    if result.get("TP/SL hit", True):
                        logger.info(f"Take profit or stop loss hit for {symbol}, holding position.")
                        return
                    size = self.calculate_position_size()
                    if size: 
                        logger.info(f"Current exposure within threshold. Scaling position for {symbol}.")
                        self.entry_position(symbol, size, direction)

            # existing long position
            elif current_position_size > 0.0:
                if result.get("TP/SL hit", True):
                    logger.info(f"Take profit or stop loss hit for {symbol}, closing long position.")
                    closing_direction = self.get_closing_direction(current_position_size)
                    self.entry_position(symbol, current_position_size, closing_direction)
        else:
            logger.info(f"Holding position for {symbol} as no valid signal received.")

    def manage_position(self, symbol:str, atr_multiplier:float=1.0):
        logger.info(f"Managing position for {symbol}.")

        ## from portfolio manager
        portfolio_stats = self.portfolio_manager.get_portfolio_stats_by_symbol(symbol)

        position = portfolio_stats.get('position')
        entry_price = float(position.get('average_price', '0.0')) if position else 0.0 # filled price
        current_position_size = round(position.get('qty', 0.0) if position else 0.0, 8)
        unrealized_pnl = portfolio_stats.get('unrealized_pnl', 0.0)

        if symbol not in self.df_orderbook or self.df_orderbook[symbol].empty:
            logger.warning(f"No orderbook data available for {symbol}. Available symbols: {list(self.df_orderbook.keys())}")

        current_price = self.df_orderbook[symbol]['mid_price'].iloc[-1]


        if not self.current_atr:
            return  {
                "TP/SL hit": False,
            }

        current_atr = float(self.current_atr)

        # TODO: think of how to handle this
        # set threshold to deal with error in case of extremely small position size
        position_size_threshold = 1e-10

        if abs(current_position_size) < position_size_threshold:
            current_position_size = 0.0

        if current_position_size > 0.0:
            direction = "LONG"
        elif current_position_size < 0.0:
            direction = "SHORT"
        else:
            direction = "FLAT"
            logger.info(f"No open position to manage for {symbol}.")
            return{
                "TP/SL hit": False,
                "new_sl": None,
                "new_tp": None,
                'r_multiple': 0.0,
                'pnl_pct': 0.0,
            }

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
    def drawdown_limit_check(self, symbol) -> bool:
        logger.info(f"Checking drawdown limits for {symbol}.")

        if not self.real_data_initialized:
            self.initialize_drawdown_tracking()

        portfolio_value = self.get_portfolio_value()

        # skip drawdown check
        if portfolio_value <= 0:
            logger.info(f"Portfolio value is {portfolio_value}, skipping drawdown check until data is available.")
            return False, 0.0, 0.0

        if self.peak_value is None:
            self.peak_value = portfolio_value
        if self.initial_value is None:
            self.initial_value = portfolio_value

        # update peak value
        self.peak_value = max(self.peak_value, portfolio_value)

        relative_dd = (self.peak_value - portfolio_value) / self.peak_value if self.peak_value > 0 else 0.0
        absolute_dd = (self.initial_value - portfolio_value) / self.initial_value if self.initial_value > 0 else 0.0

        logger.info(f"Drawdown metrics - Relative: {relative_dd:.2%}, Absolute: {absolute_dd:.2%}")

        # drawdown checks
        if self.peak_value > 0 and self.initial_value > 0:
            if relative_dd >= self.max_relative_drawdown or absolute_dd >= self.max_absolute_drawdown:
                logger.critical(f"Drawdown limits breached! Relative dd: {relative_dd:.2%}, Absolute dd: {absolute_dd:.2%}")

                logger.critical("Initiating emergency liquidation due to drawdown breach...")
                self.emergency_liquidation()

                self.circuit_breaker.force_open(f"Drawdown limit breached for {symbol}.")

                return True, relative_dd, absolute_dd
        else:
            logger.info("Skipping drawdown check - insufficient data for calculation.")

        return False, relative_dd, absolute_dd

    def get_positions_from_binance(self) -> dict:
        try:
            positions_data = self.api.get_current_position()
            positions = {}

            if isinstance(positions_data, list):
                for position in positions_data:
                    symbol = position.get('symbol')
                    qty = float(position.get('positionAmt', 0))

                    if qty != 0:
                        positions[symbol] = {
                            'qty': qty,
                            'entry_price': float(position.get('entryPrice', 0)),
                            'unrealized_pnl': float(position.get('unRealizedProfit', 0)),
                            'mark_price': float(position.get('markPrice', 0))
                        }
            else:
                logger.error(f"Unexpected response format from get_current_position: {positions_data}")

            logger.info(f"Real positions from Binance: {positions}")
            return positions

        except Exception as e:
            logger.error(f"Error getting real positions from Binance: {e}")
            return {}

    def liquidate_positions(self) -> bool:
        logger.critical("Liquidating real positions from Binance.")

        positions = self.get_positions_from_binance()

        if not positions:
            logger.info("No positions to liquidate.")
            return True

        liquidation_success = True

        for symbol, position in positions.items():
            try:
                qty = abs(position['qty'])
                direction = "SELL" if position['qty'] > 0 else "BUY"

                logger.critical(f"Liquidating {symbol}: {qty} via {direction}")

                self.api.place_market_order(
                    symbol=symbol,
                    side=direction,
                    qty=qty
                )

                logger.critical(f"Liquidation order placed for {symbol}: {qty} {direction}")

            except Exception as e:
                logger.error(f"Failed to liquidate position for {symbol}: {e}")
                liquidation_success = False

        return liquidation_success

    def emergency_liquidation(self) -> bool:
        logger.critical("Emergency Shutdown: Circuit breaker triggered. Liquiding all positions.")

        self.emergency_shutdown = True

        positions_summary = self.get_positions_from_binance()
        logger.critical(f"Real positions before liquidation: {positions_summary}")

        # Liquidate real positions from Binance
        liquidation_success = self.liquidate_positions()

        if liquidation_success:
            logger.critical("All positions have been closed.")
        else:
            logger.critical("Some positions could not be closed.")

        return liquidation_success

    def is_emergency_shutdown(self) -> bool:
        return self.emergency_shutdown

    def check_circuit_breaker_status(self) -> bool:
        if self.circuit_breaker.get_state() == "open":
            if not self.emergency_shutdown:
                logger.critical("Circuit breaker is open- triggering emergency shutdown")
                self.emergency_liquidation()
            return True
        return False

    def initialize_drawdown_tracking(self):
        try:
            logger.info("Initializing drawdown tracking with binance data...")

            balance_data = self.api.get_account_balance()
            real_balance = 0.0

            if isinstance(balance_data, list):
                for balance in balance_data:
                    if balance.get('asset') == 'USDT':
                        real_balance = float(balance.get('balance', 0))
                        break

            positions_data = self.api.get_current_position()
            total_unrealized_pnl = 0.0

            if isinstance(positions_data, list):
                for position in positions_data:
                    qty = float(position.get('positionAmt', 0))
                    if qty != 0:
                        unrealized_pnl = float(position.get('unRealizedProfit', 0))
                        total_unrealized_pnl += unrealized_pnl

            real_portfolio_value = real_balance + total_unrealized_pnl

            self.initial_value = real_portfolio_value
            self.peak_value = real_portfolio_value
            self.real_data_initialized = True

            logger.info(f"Drawdown tracking initialized - Initial value: {self.initial_value}, Peak value: {self.peak_value}")
            logger.info(f"Real balance: {real_balance}, Total unrealized PnL: {total_unrealized_pnl}")

        except Exception as e:
            logger.error(f"Failed to initialize drawdown tracking with real data: {e}")
            self.real_data_initialized = False

    def get_portfolio_value(self) -> float:
        try:
            balance_data = self.api.get_account_balance()
            print(f"Balance data: {balance_data}!!!!!!!!!!!!!!!!!!!!!!!!")
            real_balance = 0.0

            if isinstance(balance_data, list):
                for balance in balance_data:
                    if balance.get('asset') == 'USDT':
                        real_balance = float(balance.get('balance', 0))
                        break

            # get positions and calculate total unrealized PnL
            positions_data = self.api.get_current_position()
            total_unrealized_pnl = 0.0

            if isinstance(positions_data, list):
                for position in positions_data:
                    qty = float(position.get('positionAmt', 0))
                    if qty != 0:
                        unrealized_pnl = float(position.get('unRealizedProfit', 0))
                        total_unrealized_pnl += unrealized_pnl

            real_portfolio_value = real_balance + total_unrealized_pnl
            return real_portfolio_value

        except Exception as e:
            logger.error(f"Error getting actual portfolio value: {e}")
            return 0.0








        


        



        




    

    






    

