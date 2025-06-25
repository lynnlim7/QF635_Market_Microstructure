
from app.api.base_api import BaseApi
from app.common.interface_order import Side
from app.utils.func import get_execution_channel
from app.utils.logger import main_logger as logger
import random


class MockBinanceApi(BaseApi):

    def __init__(self, symbol:str, redis_publisher):
        logger.info("INSTANTIATING MOCK API")

        self._symbol = symbol.lower() # just to standardise
        self.last_market_price = {} # {symbol (upper Case): {"best_bid": float, "best_ask":float} }
        self.publisher = redis_publisher

    def place_market_order(self, symbol: str, side: str, qty: float):
        """
        Place a market order.
        """
        print("Placing market order now!!!!!!!!!!!!!!!!")

        if side == Side.BUY.name:
            # TODO: handle multiple ccy
            market_price = self.last_market_price[self._symbol.upper()]['best_ask']
        elif side == Side.SELL.name:
            market_price = self.last_market_price[self._symbol.upper()]['best_bid']
        else:
            raise ValueError(f"Invalid side: {side}")

        order_id = random.randint(1_000_000_000, 9_999_999_999)
        timestamp = self.last_market_price[self._symbol.upper()]['timestamp']

        new_qty = round(qty, 3)
        evt = {
            'symbol': 'BTCUSDT',
            'order_id': order_id,
            'client_order_id': str(order_id),
            'side': side,
            'position_side': 'BOTH',
            'exec_type': 'TRADE',
            'status': 'FILLED',
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': new_qty,
            'cum_filled_qty': new_qty,
            'avg_price': market_price,
            'last_qty': new_qty,
            'last_price': market_price,
            'commission': round(market_price * float(qty) * 0.0004, 8),
            'realized_pnl': 0.0,
            'is_maker': False,
            'event_time_ms': timestamp,
            'trade_time_ms': timestamp,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }

        if self.publisher:
            execution_channel = get_execution_channel(self._symbol)
            self.publisher.publish(execution_channel, evt)

        pass

    def place_limit_order(self, side: Side, price, quantity, tif='IOC'):
        """
        Place a limit order.
        """
        pass

    def cancel_order(self, order_id):
        """
        Cancel an existing order.
        """
        pass

    def get_current_position(self):
        """
        Retrieve current position data.
        """
        pass

    def get_ohlcv(self, symbol, interval, limit):
        """
        Fetch OHLCV (candlestick) data.
        """
        # TODO: NEED TO IMPLETEMENT
        pass

    def get_account_balance(self) -> dict:
        """
        Fetch OHLCV (candlestick) data.
        """
        # TODO: NEED TO IMPLETEMENT
        pass

    def on_new_price(self, data: dict):
        symbol = data.get('contract_name').upper()
        if not symbol:
            logger.warn("Missing symbol in new price, will not process")
            return

        bids = data.get('bids')
        asks = data.get('asks')
        timestamp = data.get('timestamp')

        best_bid = bids[0].get('price') if len(bids) != 0 else 0
        best_ask = asks[0].get('price') if len(asks) != 0 else 0
        # logger.info(f"New Price into portfolio Manager symb: {symbol}, best_bid: {best_bid}, best_ask: {best_ask}")
        self.last_market_price[symbol] = {
            'timestamp': timestamp,
            'best_bid': best_bid,
            'best_ask': best_ask
        }
        # print(f"saved last market price {self.last_market_price}")
