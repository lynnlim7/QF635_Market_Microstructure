from app.common.order_event_update import OrderEventUpdate
from app.utils.logger import main_logger as logger
from models import ExecutionType, OrderSide, OrderStatus


class PortfolioManager:
    def __init__(self):
        self.positions = {}  # {symbol (Upper Case): {"qty": float, "average_price": float}}
        self.realized_pnl = 0.0
        self.unrealized_pnl = {} # {symbol (upper Case): float } e.g. {"BTCUSDT":3.4,"ETHUSDT":-1.3}
        self.last_market_price = {} # {symbol (upper Case): {"best_bid": float, "best_ask":float} }
        self.total_commissions = 0.0

        self.open_orders = [] # to be determined
        self.trade_history: list[OrderEventUpdate] = []


    def on_new_trade(self, data: dict):
        if data['exec_type'] != ExecutionType.TRADE.name:
            return
        if data['status'] != OrderStatus.FILLED.name:
            return

        logger.info(f"New Trade into portfolio Manager {data}")
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
        if final_qty == 0.0 or not last_price:
            return
        if final_qty > 0:
            if last_price['best_bid'] != 0.0:
                self.unrealized_pnl[symbol] = final_qty * (last_price['best_bid'] - final_price)
                return

        if final_qty < 0:
            if last_price['best_ask'] != 0.0:
                self.unrealized_pnl[symbol] = abs(final_qty) * (final_price - last_price['best_ask'])
                return
        return

    def on_new_price(self, data: dict):
        symbol = data.get('contract_name').upper()
        if not symbol:
            logger.warn("Missing symbol in new price, will not process")
            return

        bids = data.get('bids')
        asks = data.get('asks')

        best_bid = bids[0].get('price') if len(bids) != 0 else 0
        best_ask = asks[0].get('price') if len(asks) != 0 else 0
        logger.info(f"New Price into portfolio Manager symb: {symbol}, best_bid: {best_bid}, best_ask: {best_ask}")
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
            'total_pnl': self.get_total_pnl(),
            'cash_balance': self.cash # placeholder 
        }

    def get_positions(self):
        return self.positions

    def get_realized_pnl(self):
        return self.realized_pnl

if __name__=="__main__" :
    symbol = 'BTCUSDT'

    port = PortfolioManager()


    trade = {'symbol': 'BTCUSDT', 'order_id': 4525164108, 'client_order_id': 'web_EFSZLtm94RjlFphDNKLg', 'side': 'BUY',
     'position_side': 'BOTH', 'exec_type': 'TRADE', 'status': 'FILLED', 'order_type': 'MARKET', 'time_in_force': 'GTC',
     'orig_qty': 1, 'cum_filled_qty': 1, 'avg_price': 100, 'last_qty': 1, 'last_price': 100,
     'commission': 0.04212276, 'realized_pnl': 0.48545, 'is_maker': False, 'event_time_ms': 1749876626477,
     'trade_time_ms': 1749876626476, 'stop_price': 0.0, 'activation_price': 0.0, 'callback_rate': 0.0}

    # trade = {'symbol':'BTCUSDT', 'exec_type': 'TRADE', 'status': 'FILLED', 'side': 'BUY'}

    print(port.on_new_trade(trade))
    print(port.get_portfolio_stats_by_symbol(symbol))

    price = {'contract_name': 'btcusdt', 'timestamp': 1749875536466,
     'bids': [{'price': 99, 'quantity': 0.256}],
     'asks': [{'price': 101, 'quantity': 0.677}]}

    port.on_new_price(price)
    print(port.get_portfolio_stats_by_symbol(symbol))
