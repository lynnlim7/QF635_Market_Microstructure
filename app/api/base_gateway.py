from abc import ABC, abstractmethod


class BaseGateway(ABC):
    @abstractmethod
    def __init__(self):
        """Initialize the strategy with symbol and config."""
        pass

    @abstractmethod
    def connection(self):
        """
        Abstract method to establish connection.
        Implement this in concrete gateway classes (e.g. BinanceGateway).
        """
        pass