
import pandas as pd
import pytest
import logging

from app.bot.risk.risk_manager import RiskManager
from app.bot.api.binance_gateway import BinanceGateway
from app.bot.portfolio.PortfolioManager import PortfolioManager
from app.bot.strategy.macd_strategy import MACDStrategy

from app.bot.utils.config import settings


@pytest.fixture
def sample_orderbook():
    return {
        "bids": [{"price": "100.0"}],
        "asks": [{"price": "101.0"}],
        "timestamp": 1747732320000
    }

@pytest.fixture
def sample_candlestick():
    return {
        "open": 100.0, "close": 101.0, "high": 102.0, "low": 99.0,
        "volume": 10.0, "is_closed": True, "start_time": 1747732320000
    }

@pytest.fixture
def mock_components():
    class DummyGateway:
        def place_limit_order(self, **kwargs):
            return {"order_id": 1}

    class DummyPM:
        def get_cash(self):
            return 10000

        get_positions = {"BTCUSDT": {"qty": 1}}

    class DummyMACD:
        def generate_signal(self):
            return settings.SIGNAL_SCORE_BUY # Buy

    return DummyGateway(), DummyPM(), DummyMACD(), DummyMACD()

@pytest.fixture
def dummy_logger():
    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.CRITICAL)  # suppress during tests
    return logger

def test_entry_position(sample_orderbook, sample_candlestick, mock_components):
    api, portfolio_manager, trade_signal, trade_direction = mock_components
    risk_manager = RiskManager(
        api=api,
        portfolio_manager=portfolio_manager,
        trade_signal=trade_signal,
        trade_direction=trade_direction,
        logger=dummy_logger
    )

    # Simulate data ingestion
    risk_manager.data_aggregator(sample_orderbook)
    risk_manager.process_candlestick(sample_candlestick)
    
    # Simulate entry
    stop_loss, take_profit = risk_manager.entry_position(current_price=100.5, current_prices={"BTCUSDT": 100.5}, api=api)
    
    assert stop_loss is not None
    assert take_profit is not None
    assert risk_manager.active_trades["trade_direction"] == "BUY"