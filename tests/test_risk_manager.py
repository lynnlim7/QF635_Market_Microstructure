import pytest
import os
from app.risk.risk_manager import RiskManager
from app.api.binance_api import BinanceApi
from app.api.binance_gateway import BinanceGateway
from app.portfolio.portfolio_manager import PortfolioManager
from app.strategy.macd_strategy import MACDStrategy
from app.utils.config import settings
import time
import pandas as pd
import numpy as np
from queue import Queue
import threading
from app.services import RedisPool
from app.utils.func import get_execution_channel, get_orderbook_channel, get_candlestick_channel
from app.services.circuit_breaker import RedisCircuitBreaker
from app.queue_manager.locking_queue import LockingQueue

class MockBinanceApi:
    def __init__(self):
        self.orders = []
        self.open_orders = []

    def place_market_order(self, symbol, side, type, qty):
        self.orders.append({
            'symbol': symbol,
            'side': side,
            'type': type,
            'qty': qty
        })
        return {'orderId': len(self.orders)}

    def place_stop_loss(self, side, type, qty, symbol, price, tif):
        order = {
            'symbol': symbol,
            'side': side,
            'type': 'STOP_LOSS',  # Fixed type
            'qty': qty,
            'price': price,
            'tif': tif,
            'stopPrice': price  # Added stopPrice for stop orders
        }
        self.open_orders.append(order)
        return {'orderId': len(self.open_orders)}

    def place_take_profit_order(self, side, type, qty, symbol, price, tif):
        order = {
            'symbol': symbol,
            'side': side,
            'type': 'TAKE_PROFIT',  # Fixed type
            'qty': qty,
            'price': price,
            'tif': tif,
            'stopPrice': price  # Added stopPrice for take profit orders
        }
        self.open_orders.append(order)
        return {'orderId': len(self.open_orders)}

    def get_open_orders(self, symbol):
        return self.open_orders

    def cancel_open_orders(self, symbol):
        self.open_orders = []
        return True

    def cancel_order(self, symbol):
        if self.open_orders:
            self.open_orders.pop()
        return True

class MockCircuitBreaker:
    def __init__(self):
        self.is_open = False

    def allow_request(self):
        return not self.is_open

    def force_open(self, reason):
        self.is_open = True

@pytest.fixture
def mock_api():
    return MockBinanceApi()

@pytest.fixture
def mock_circuit_breaker():
    return MockCircuitBreaker()

@pytest.fixture
def portfolio_manager():
    return PortfolioManager()

@pytest.fixture
def risk_manager(mock_api, portfolio_manager, mock_circuit_breaker):
    return RiskManager(
        symbol="BTCUSDT",
        api=mock_api,
        portfolio_manager=portfolio_manager,
        circuit_breaker=mock_circuit_breaker,
        max_risk_per_trade_pct=0.02,
        max_absolute_drawdown=0.1,
        max_relative_drawdown=0.15,
        max_exposure_pct=0.5
    )

def create_mock_orderbook_data(symbol="BTCUSDT", timestamp=None):
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    return {
        'symbol': symbol,
        'timestamp': timestamp,
        'bids': [{'price': '50000.0', 'quantity': '1.0'}],
        'asks': [{'price': '50001.0', 'quantity': '1.0'}]
    }

def create_mock_candlestick_data(symbol="BTCUSDT", timestamp=None):
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    return {
        'symbol': symbol,
        'start_time': timestamp,
        'open': '50000.0',
        'high': '50100.0',
        'low': '49900.0',
        'close': '50050.0',
        'volume': '100.0'
    }

def create_mock_trade_data(symbol="BTCUSDT", side="BUY", qty=1.0, price=50000.0):
    return {
        'symbol': symbol,
        'order_id': 12345,
        'client_order_id': 'test_order_123',
        'side': side,
        'position_side': 'BOTH',
        'exec_type': 'TRADE',
        'status': 'FILLED',
        'order_type': 'MARKET',
        'time_in_force': 'GTC',
        'orig_qty': str(qty),
        'cum_filled_qty': str(qty),
        'avg_price': str(price),
        'last_qty': str(qty),
        'last_price': str(price),
        'commission': '0.1',
        'realized_pnl': '0.0',
        'is_maker': False,
        'event_time_ms': int(time.time() * 1000),
        'trade_time_ms': int(time.time() * 1000),
        'stop_price': '0.0',
        'activation_price': '0.0',
        'callback_rate': '0.0'
    }

class TestRiskManager:
    def test_process_orderbook(self, risk_manager):
        # Test orderbook processing
        orderbook_data = create_mock_orderbook_data()
        risk_manager.process_orderbook(orderbook_data)
        
        assert "BTCUSDT" in risk_manager.df_orderbook
        assert not risk_manager.df_orderbook["BTCUSDT"].empty
        assert risk_manager.df_orderbook["BTCUSDT"].iloc[-1]['mid_price'] == 50000.5

    def test_process_candlestick(self, risk_manager):
        # Test candlestick processing
        candlestick_data = create_mock_candlestick_data()
        risk_manager.process_candlestick(candlestick_data)
        
        assert "BTCUSDT" in risk_manager.df_candlestick
        assert not risk_manager.df_candlestick["BTCUSDT"].empty
        assert risk_manager.df_candlestick["BTCUSDT"].iloc[-1]['close'] == 50050.0

    def test_calculate_atr(self, risk_manager):
        # Create multiple candlesticks to calculate ATR
        for i in range(20):
            timestamp = int(time.time() * 1000) - (20 - i) * 60000
            candlestick_data = create_mock_candlestick_data(timestamp=timestamp)
            risk_manager.process_candlestick(candlestick_data)
        
        atr = risk_manager.calculate_atr()
        assert atr is not None
        assert atr > 0

    def test_calculate_position_size(self, risk_manager):
        # Setup required data
        orderbook_data = create_mock_orderbook_data()
        risk_manager.process_orderbook(orderbook_data)
        
        for i in range(20):
            timestamp = int(time.time() * 1000) - (20 - i) * 60000
            candlestick_data = create_mock_candlestick_data(timestamp=timestamp)
            risk_manager.process_candlestick(candlestick_data)
        
        position_size = risk_manager.calculate_position_size()
        assert position_size is not None
        assert position_size > 0

    def test_accept_signal(self, risk_manager):
        # Setup required data
        orderbook_data = create_mock_orderbook_data()
        risk_manager.process_orderbook(orderbook_data)
        
        # Setup candlestick data for ATR calculation
        for i in range(20):
            timestamp = int(time.time() * 1000) - (20 - i) * 60000
            candlestick_data = create_mock_candlestick_data(timestamp=timestamp)
            risk_manager.process_candlestick(candlestick_data)
        
        # Setup portfolio stats with some initial value
        trade_data = create_mock_trade_data(side="BUY", qty=0.1, price=50000.0)
        risk_manager.portfolio_manager.on_new_trade(trade_data)
        
        # Update portfolio with some PnL and market price
        risk_manager.portfolio_manager.realized_pnl = 1000.0  # Add some realized PnL
        risk_manager.portfolio_manager.unrealized_pnl = {"BTCUSDT": 500.0}  # Add some unrealized PnL
        
        # Update market price in portfolio manager
        price_data = {
            'contract_name': 'btcusdt',
            'bids': [{'price': 50000.0, 'quantity': 1.0}],
            'asks': [{'price': 50001.0, 'quantity': 1.0}]
        }
        risk_manager.portfolio_manager.on_new_price(price_data)
        
        # Ensure orderbook data is properly set in risk manager
        current_time = pd.Timestamp.now()
        risk_manager.df_orderbook = {
            "BTCUSDT": pd.DataFrame([{
                'timestamp': current_time,
                'symbol': 'BTCUSDT',
                'best_bid': 50000.0,
                'best_ask': 50001.0,
                'mid_price': 50000.5,
                'spread': 1.0,
                'spread_pct': 0.00002
            }]).set_index('timestamp')
        }
        
        # Ensure position is properly set in portfolio manager
        risk_manager.portfolio_manager.positions = {
            "BTCUSDT": {
                'qty': 0.1,
                'average_price': 50000.0
            }
        }
        
        # Print debug information
        print("Portfolio stats before signal:", risk_manager.portfolio_manager.get_portfolio_stats_by_symbol("BTCUSDT"))
        print("Orderbook data:", risk_manager.df_orderbook["BTCUSDT"])
        
        # Test buy signal
        direction = risk_manager.accept_signal(1, "BTCUSDT")  # 1 for buy
        print("Signal direction:", direction)
        assert direction == "BUY"
        
        # Test sell signal
        direction = risk_manager.accept_signal(-1, "BTCUSDT")  # -1 for sell
        assert direction == "SELL"
        
        # Test hold signal
        direction = risk_manager.accept_signal(0, "BTCUSDT")  # 0 for hold
        assert direction is None
        
        # Test max exposure limit
        # Create a large position to trigger max exposure
        large_trade = create_mock_trade_data(side="BUY", qty=10.0, price=50000.0)
        risk_manager.portfolio_manager.on_new_trade(large_trade)
        direction = risk_manager.accept_signal(1, "BTCUSDT")
        assert direction is None  # Should return None due to max exposure

    def test_entry_position(self, risk_manager):
        # Setup required data
        orderbook_data = create_mock_orderbook_data()
        risk_manager.process_orderbook(orderbook_data)
        
        for i in range(20):
            timestamp = int(time.time() * 1000) - (20 - i) * 60000
            candlestick_data = create_mock_candlestick_data(timestamp=timestamp)
            risk_manager.process_candlestick(candlestick_data)
        
        # Test entry position
        entry_signal = risk_manager.entry_position("BTCUSDT", "BUY")
        assert entry_signal is not None
        stop_loss, take_profit = entry_signal
        assert stop_loss < take_profit

    def test_manage_position(self, risk_manager):
        # Setup required data
        orderbook_data = create_mock_orderbook_data()
        risk_manager.process_orderbook(orderbook_data)
        
        # Setup candlestick data for ATR calculation
        for i in range(20):
            timestamp = int(time.time() * 1000) - (20 - i) * 60000
            candlestick_data = create_mock_candlestick_data(timestamp=timestamp)
            risk_manager.process_candlestick(candlestick_data)
        
        # Verify ATR calculation
        atr = risk_manager.calculate_atr()
        print("\nATR value:", atr)
        assert atr is not None, "ATR calculation failed"
        
        # Create a position first
        trade_data = create_mock_trade_data(side="BUY", qty=1.0, price=50000.0)
        risk_manager.portfolio_manager.on_new_trade(trade_data)
        
        # Update market price in portfolio manager
        price_data = {
            'contract_name': 'btcusdt',
            'bids': [{'price': 50000.0, 'quantity': 1.0}],
            'asks': [{'price': 50001.0, 'quantity': 1.0}]
        }
        risk_manager.portfolio_manager.on_new_price(price_data)
        
        # Ensure orderbook data is properly set in risk manager
        current_time = pd.Timestamp.now()
        df_orderbook = pd.DataFrame([{
            'timestamp': current_time,
            'symbol': 'BTCUSDT',
            'best_bid': 50000.0,
            'best_ask': 50001.0,
            'mid_price': 50000.5,
            'spread': 1.0,
            'spread_pct': 0.00002
        }]).set_index('timestamp')
        
        # Print debug information before setting orderbook
        print("\nBefore setting orderbook:")
        print("df_orderbook shape:", df_orderbook.shape)
        print("df_orderbook columns:", df_orderbook.columns)
        print("df_orderbook data:", df_orderbook)
        
        risk_manager.df_orderbook = {"BTCUSDT": df_orderbook}
        
        # Print debug information after setting orderbook
        print("\nAfter setting orderbook:")
        print("df_orderbook keys:", risk_manager.df_orderbook.keys())
        print("BTCUSDT data:", risk_manager.df_orderbook["BTCUSDT"])
        
        # Ensure position is properly set in portfolio manager
        risk_manager.portfolio_manager.positions = {
            "BTCUSDT": {
                'qty': 1.0,
                'average_price': 50000.0
            }
        }
        
        # Update portfolio with some unrealized PnL to trigger position management
        risk_manager.portfolio_manager.unrealized_pnl = {"BTCUSDT": 100.0}
        
        # Print debug information
        print("\nPortfolio stats before management:", risk_manager.portfolio_manager.get_portfolio_stats_by_symbol("BTCUSDT"))
        
        # Calculate expected stop loss and take profit levels
        entry_price = 50000.0
        current_price = 50000.5
        risk = atr * 1.0  # Using atr_multiplier=1.0
        
        # For a long position with positive PnL
        expected_sl = entry_price - risk  # Initial stop loss
        expected_tp = current_price + (2 * risk)  # Initial take profit
        
        print("\nExpected levels:")
        print(f"Entry price: {entry_price}")
        print(f"Current price: {current_price}")
        print(f"ATR: {atr}")
        print(f"Risk: {risk}")
        print(f"Expected stop loss: {expected_sl}")
        print(f"Expected take profit: {expected_tp}")
        
        # Test position management
        risk_manager.manage_position("BTCUSDT", atr_multiplier=1.0)
        
        # Print debug information
        print("\nOpen orders:", risk_manager.api.open_orders)
        
        # Verify that stop loss and take profit orders were placed
        assert len(risk_manager.api.open_orders) > 0, "No orders were placed"
        
        # Verify the types of orders placed
        order_types = [order['type'] for order in risk_manager.api.open_orders]
        print("\nOrder types placed:", order_types)
        assert 'STOP_LOSS' in order_types, "No stop loss order was placed"
        assert 'TAKE_PROFIT' in order_types, "No take profit order was placed"
        
        # Verify order prices
        for order in risk_manager.api.open_orders:
            print(f"\nOrder details: {order}")
            if order['type'] == 'STOP_LOSS':
                assert abs(float(order['stopPrice']) - expected_sl) < 0.1, f"Stop loss price {order['stopPrice']} does not match expected {expected_sl}"
            elif order['type'] == 'TAKE_PROFIT':
                assert abs(float(order['stopPrice']) - expected_tp) < 0.1, f"Take profit price {order['stopPrice']} does not match expected {expected_tp}"

    def test_calculate_drawdown_limits(self, risk_manager):
        # Setup required data
        orderbook_data = create_mock_orderbook_data()
        risk_manager.process_orderbook(orderbook_data)
        
        for i in range(20):
            timestamp = int(time.time() * 1000) - (20 - i) * 60000
            candlestick_data = create_mock_candlestick_data(timestamp=timestamp)
            risk_manager.process_candlestick(candlestick_data)
        
        # Test drawdown limits
        current_prices = {"BTCUSDT": 50000.0}
        result = risk_manager.calculate_drawdown_limits("BTCUSDT", current_prices)
        assert result is True  # Should be True as no drawdown has occurred yet
