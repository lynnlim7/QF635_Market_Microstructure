from abc import ABC, abstractmethod
from app.common.interface_order import Side


class BaseApi(ABC):

    @abstractmethod
    def place_market_order(self, symbol: str, side: str, qty: float):
        """
        Place a market order.
        """
        pass

    @abstractmethod
    def place_limit_order(self, side: Side, price, quantity, tif='IOC'):
        """
        Place a limit order.
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id):
        """
        Cancel an existing order.
        """
        pass

    @abstractmethod
    def get_current_position(self):
        """
        Retrieve current position data.
        """
        pass

    @abstractmethod
    def get_ohlcv(self, symbol, interval, limit):
        """
        Fetch OHLCV (candlestick) data.
        """
        pass
