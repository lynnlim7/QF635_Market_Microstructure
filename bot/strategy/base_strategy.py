
from abc import ABC, abstractmethod

from bot.client.binance_api import BinanceApi


class BaseStrategy(ABC):
    @abstractmethod
    def __init__(self, symbol: str,api: BinanceApi, config: dict = None):
        """Initialize the strategy with symbol and config."""
        pass

    @abstractmethod
    def update_data(self, data):
        """Feed new live or simulated data into the strategy."""
        pass

    @abstractmethod
    def generate_signal(self) -> int:
        """Generate trading signal: 1=Buy, -1=Sell, 0=Hold."""
        pass

    @abstractmethod
    def get_state(self) -> dict:
        """Return current strategy state (for logs or dashboard)."""
        pass
