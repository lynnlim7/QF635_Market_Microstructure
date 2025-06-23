import pandas as pd
from tensorflow import timestamp

from app.analytics.TradeAnalysis import TradeAnalysis
from app.common.order_event_update import OrderEventUpdate
from app.utils.logger import main_logger as logger
from models import ExecutionType, OrderSide, OrderStatus
import traceback


class PortfolioManager:
    def __init__(self):
        self.positions = {}  # {symbol (Upper Case): {"qty": float, "average_price": float}}
        self.realized_pnl = 0.0
        self.unrealized_pnl = {} # {symbol (upper Case): float } e.g. {"BTCUSDT":3.4,"ETHUSDT":-1.3}
        self.last_market_price = {} # {symbol (upper Case): {"best_bid": float, "best_ask":float} }
        self.total_commissions = 0.0
        self.cash = 0.0 # placeholder

        self.open_orders = [] # to be determined
        self.trade_history: list[OrderEventUpdate] = []
        self.trade_history_dict: list[dict] = []


    def on_new_trade(self, data: dict):
        try:
            if data['exec_type'] != ExecutionType.TRADE.name:
                return
            if data['status'] != OrderStatus.FILLED.name:
                return

            logger.info(f"New Trade into portfolio Manager {data}")
            self.trade_history_dict.append(data) # quick fix for getting data
            trade_event = OrderEventUpdate.from_dict(data)
            self.trade_history.append(trade_event)

            self.total_commissions += float(trade_event.commission)

            symbol = trade_event.symbol.upper()  # Ensure symbol is uppercased for consistency
            is_buy = trade_event.side == OrderSide.BUY.name
            filled_qty = float(trade_event.last_qty) if is_buy else -float(trade_event.last_qty)
            filled_price = float(trade_event.last_price)

            current_position = self.positions.get(symbol)

            final_qty = 0.0
            final_price = 0.0

            if not current_position or current_position['qty'] == 0 or current_position['average_price'] == 0:
                # Open a new position
                final_qty = filled_qty
                final_price = filled_price
            else:
                current_qty = current_position['qty']
                average_price = current_position['average_price']

                # if buy order
                if current_qty > 0:
                    if filled_qty > 0:
                        # increase long position
                        final_price = (current_qty * average_price + filled_qty * filled_price) / (current_qty + filled_qty)
                        final_qty = current_qty + filled_qty
                    elif filled_qty < 0:
                        # reduce long position
                        if abs(filled_qty) < current_qty:
                            final_price = average_price
                            final_qty = current_qty + filled_qty
                            self.realized_pnl += (filled_price - average_price) * abs(filled_qty)
                        # square off position
                        elif abs(filled_qty) == current_qty:
                            self.realized_pnl += (filled_price - average_price) * abs(filled_qty)
                        # sell more than owned
                        elif abs(filled_qty) > current_qty:
                            final_qty = current_qty + filled_qty
                            final_price = filled_price
                            self.realized_pnl += (filled_price - average_price) * abs(current_qty)
                # if sell order
                elif current_qty < 0:
                    if filled_qty < 0:
                        # increase short position
                        final_price = (abs(current_qty) * average_price + abs(filled_qty) * filled_price) / (abs(current_qty + filled_qty))
                        final_qty = current_qty + filled_qty
                    elif filled_qty > 0:
                        # reduce short position
                        if filled_qty < abs(current_qty):
                            final_price = average_price
                            final_qty = current_qty + filled_qty
                            self.realized_pnl += (average_price - filled_price) * abs(filled_qty)
                        # square off short position
                        elif filled_qty == abs(current_qty):
                            self.realized_pnl += (average_price - filled_price) * abs(filled_qty)
                        # buy back more than sell
                        elif filled_qty > abs(current_qty):
                            self.realized_pnl += (average_price - filled_price) * abs(current_qty)
                            final_price = filled_price
                            final_qty = current_qty + filled_qty

            self.positions[symbol] = {
                'qty': final_qty,
                'average_price': final_price
            }
            # see if there is a need to calculate the pnl immediately
            last_price = self.last_market_price.get(symbol)

            # calculate unrealized_pnl
            if final_qty > 0:
                if last_price['best_bid'] != 0.0:
                    self.unrealized_pnl[symbol] = final_qty * (last_price['best_bid'] - final_price)


            if final_qty < 0:
                if last_price['best_ask'] != 0.0:
                    self.unrealized_pnl[symbol] = abs(final_qty) * (final_price - last_price['best_ask'])

            self.print_state()
        except Exception as err:
            logger.error(f"FAILED TO ACCEPT TRADE: {err}")
            traceback.print_exc()


    def on_new_price(self, data: dict):
        symbol = data.get('contract_name').upper()
        if not symbol:
            logger.warn("Missing symbol in new price, will not process")
            return

        if data.get('timestamp') == -1.0:
            logger.info("ITS DONE, calculate analytics now")
            self.print_trade_analytics()
            return

        bids = data.get('bids')
        asks = data.get('asks')

        best_bid = bids[0].get('price') if len(bids) != 0 else 0
        best_ask = asks[0].get('price') if len(asks) != 0 else 0
        # logger.info(f"New Price into portfolio Manager symb: {symbol}, best_bid: {best_bid}, best_ask: {best_ask}")
        self.last_market_price[symbol] = {
            'best_bid': best_bid,
            'best_ask': best_ask
        }

        current_positions = self.positions.get(symbol)
        if not current_positions:
            return

        if current_positions['qty'] == 0:
            self.unrealized_pnl[symbol] = 0
            return

        if current_positions['qty'] > 0:
            if best_bid != 0.0:
                self.unrealized_pnl[symbol] = current_positions['qty'] * (best_bid - current_positions['average_price'])

        if current_positions['qty'] < 0:
            if best_ask != 0.0:
                self.unrealized_pnl[symbol] = abs(current_positions['qty']) * (current_positions['average_price'] - best_ask)
                return

        return


    # State Accessors
    def get_unrealised_pnl(self):
        return sum(self.unrealized_pnl.values())

    def get_total_pnl(self) -> float:
        unrealized_pnl = 0.0
        unrealized_total = sum(self.unrealized_pnl.values())
        return self.realized_pnl + unrealized_total

    def get_portfolio_stats_by_symbol(self, symbol: str):
        if not symbol:
            return {}
        return {
            'position': self.positions.get(symbol.upper()),
            'unrealized_pnl': self.unrealized_pnl.get(symbol.upper()),
            'last_market_price': self.last_market_price.get(symbol.upper()),
            'realized_pnl': self.realized_pnl,
            'total_commissions': self.total_commissions,
            "total_trade_count": len(self.trade_history),
            'total_pnl': self.get_total_pnl(),
            'cash_balance': self.cash
        }

    def get_positions(self):
        return self.positions

    def get_realized_pnl(self):
        return self.realized_pnl


    def to_dict(self):
        # Convert the class state into a dictionary
        return {
            "positions": self.positions,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "last_market_price": self.last_market_price,
            "total_commissions": self.total_commissions,
            "total_trade_count": len(self.trade_history),
            "total_pnl": self.realized_pnl + self.unrealized_pnl['BTCUSDT'],
            # "open_orders": self.open_orders,
            # "trade_history": [order.to_dict() for order in self.trade_history]  # Using `to_dict` from OrderEventUpdate
        }


    def print_state(self):
        logger.info(f"Portfolio manager state: {self.to_dict()}")
        pass

    def print_trade_analytics(self):
        self.print_state()
        logger.info(f"Trade History: {self.trade_history_dict}")
        try:
            trade_analysis = TradeAnalysis()
            trade_analysis.df = pd.DataFrame(self.trade_history_dict)
            trade_analysis.get_summary(book_size=len(self.trade_history_dict))
        except Exception as err:
            logger.error(f"failed to print trade analytics: {err}")
            traceback.print_exc()


if __name__=="__main__" :
    symbol = 'BTCUSDT'

    # port = PortfolioManager()
    # market_price = {'contract_name': 'btcusdt', 'timestamp': ,
    #  'bids': [{'price': 99, 'quantity': 0.256}],
    #  'asks': [{'price': 101, 'quantity': 0.677}]}
    # port.on_new_price(price)
    trade_history = [
        {
            "symbol": "BTCUSDT",
            "order_id": 4568376904,
            "client_order_id": "x-Cb7ytekJe40ce86314d9eabe0081ac",
            "side": "SELL",
            "position_side": "BOTH",
            "exec_type": "TRADE",
            "status": "FILLED",
            "order_type": "MARKET",
            "time_in_force": "GTC",
            "orig_qty": 0.001,
            "cum_filled_qty": 0.001,
            "avg_price": 104509.0,
            "last_qty": 0.001,
            "last_price": 104509.0,
            "commission": 0.0418036,
            "realized_pnl": 0.0,
            "is_maker": False,
            "event_time_ms": 1750399020311,
            "trade_time_ms": 1750399020311,
            "stop_price": 0.0,
            "activation_price": 0.0,
            "callback_rate": 0.0
        },
        {
            "symbol": "BTCUSDT",
            "order_id": 4568379820,
            "client_order_id": "x-Cb7ytekJe94de2d660dc34220d6aed",
            "side": "SELL",
            "position_side": "BOTH",
            "exec_type": "TRADE",
            "status": "FILLED",
            "order_type": "MARKET",
            "time_in_force": "GTC",
            "orig_qty": 0.001,
            "cum_filled_qty": 0.001,
            "avg_price": 104509.0,
            "last_qty": 0.001,
            "last_price": 104509.0,
            "commission": 0.0418036,
            "realized_pnl": 0.0,
            "is_maker": False,
            "event_time_ms": 1750399080302,
            "trade_time_ms": 1750399080301,
            "stop_price": 0.0,
            "activation_price": 0.0,
            "callback_rate": 0.0
        },
        {
            "symbol": "BTCUSDT",
            "order_id": 4568382592,
            "client_order_id": "x-Cb7ytekJ728a374ffc4cb92bc39649",
            "side": "BUY",
            "position_side": "BOTH",
            "exec_type": "TRADE",
            "status": "FILLED",
            "order_type": "MARKET",
            "time_in_force": "GTC",
            "orig_qty": 0.001,
            "cum_filled_qty": 0.001,
            "avg_price": 104509.1,
            "last_qty": 0.001,
            "last_price": 104509.1,
            "commission": 0.04180364,
            "realized_pnl": -0.0001,
            "is_maker": False,
            "event_time_ms": 1750399140312,
            "trade_time_ms": 1750399140311,
            "stop_price": 0.0,
            "activation_price": 0.0,
            "callback_rate": 0.0
        },
        {
            "symbol": "BTCUSDT",
            "order_id": 4568385293,
            "client_order_id": "x-Cb7ytekJ8c9b18365e236470e4b4ec",
            "side": "SELL",
            "position_side": "BOTH",
            "exec_type": "TRADE",
            "status": "FILLED",
            "order_type": "MARKET",
            "time_in_force": "GTC",
            "orig_qty": 0.001,
            "cum_filled_qty": 0.001,
            "avg_price": 104499.2,
            "last_qty": 0.001,
            "last_price": 104499.2,
            "commission": 0.04179968,
            "realized_pnl": 0.0,
            "is_maker": False,
            "event_time_ms": 1750399200308,
            "trade_time_ms": 1750399200308,
            "stop_price": 0.0,
            "activation_price": 0.0,
            "callback_rate": 0.0
        },
        {
            "symbol": "BTCUSDT",
            "order_id": 4568390416,
            "client_order_id": "x-Cb7ytekJ4299816d49fa545246590a",
            "side": "BUY",
            "position_side": "BOTH",
            "exec_type": "TRADE",
            "status": "FILLED",
            "order_type": "MARKET",
            "time_in_force": "GTC",
            "orig_qty": 0.001,
            "cum_filled_qty": 0.001,
            "avg_price": 104598.0,
            "last_qty": 0.001,
            "last_price": 104598.0,
            "commission": 0.0418392,
            "realized_pnl": -0.09389999,
            "is_maker": False,
            "event_time_ms": 1750399260171,
            "trade_time_ms": 1750399260171,
            "stop_price": 0.0,
            "activation_price": 0.0,
            "callback_rate": 0.0
        },
        {
            "symbol": "BTCUSDT",
            "order_id": 4568393851,
            "client_order_id": "x-Cb7ytekJ224142813f074c41855d20",
            "side": "BUY",
            "position_side": "BOTH",
            "exec_type": "TRADE",
            "status": "FILLED",
            "order_type": "MARKET",
            "time_in_force": "GTC",
            "orig_qty": 0.001,
            "cum_filled_qty": 0.001,
            "avg_price": 104599.4,
            "last_qty": 0.001,
            "last_price": 104599.4,
            "commission": 0.04183975,
            "realized_pnl": -0.0953,
            "is_maker": False,
            "event_time_ms": 1750399320201,
            "trade_time_ms": 1750399320201,
            "stop_price": 0.0,
            "activation_price": 0.0,
            "callback_rate": 0.0
        }
    ]

    for i in trade_history:
        event = OrderEventUpdate.from_dict(i)
        port.trade_history.append(event)

    port.print_state()

    trade1 =  {'symbol': 'BTCUSDT', 'order_id': 4568397035, 'client_order_id': 'x-Cb7ytekJf66b41069b2a1f5aa0c01a', 'side': 'SELL', 'position_side': 'BOTH', 'exec_type': 'TRADE', 'status': 'FILLED', 'order_type': 'MARKET', 'time_in_force': 'GTC', 'orig_qty': 0.001, 'cum_filled_qty': 0.001, 'avg_price': 104586.6, 'last_qty': 0.001, 'last_price': 104586.6, 'commission': 0.04183464, 'realized_pnl': 0.0, 'is_maker': False, 'event_time_ms': 1750399380339, 'trade_time_ms': 1750399380339, 'stop_price': 0.0, 'activation_price': 0.0, 'callback_rate': 0.0}
    port.on_new_trade(trade1)

    price = {'contract_name': 'btcusdt', 'timestamp': float(-1),
     'bids': [{'price': 99, 'quantity': 0.256}],
     'asks': [{'price': 101, 'quantity': 0.677}]}
    port.on_new_price(price)

