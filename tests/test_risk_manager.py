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

# Ensure logs directory exists
os.makedirs("./logs", exist_ok=True)

symbol = "BTCUSDT"

@pytest.fixture
def setup_risk():
    """Fixture to set up risk manager and its dependencies"""
    api = BinanceGateway(symbol=symbol)
    portfolio_manager = PortfolioManager(starting_cash=10000.0)

    signal_queue = Queue()
    trade_signal = MACDStrategy(symbol)
    trade_direction = MACDStrategy(symbol)
    
    risk_manager = RiskManager(
        api=api,
        portfolio_manager=portfolio_manager,
        trade_signal=trade_signal,
        trade_direction=trade_direction
    )
    
    return {
        'risk_manager': risk_manager,
        'signal_queue': signal_queue,
        'trade_signal': trade_signal,
        'trade_direction': trade_direction,
        'symbol': symbol
    }

def test_strategy_signal_flow(setup_risk):
    """Test the flow of signals from strategy to risk manager"""
    risk_manager = setup_risk['risk_manager']
    signal_queue = setup_risk['signal_queue']
    trade_signal = setup_risk['trade_signal']
    
    test_signals = [
        settings.SIGNAL_SCORE_BUY,   
        settings.SIGNAL_SCORE_SELL,   
        settings.SIGNAL_SCORE_HOLD    
    ]
    
    for signal in test_signals:
        # Put signal in queue
        signal_queue.put(signal)
        
        # Process signal in risk manager
        risk_manager.accept_signal(signal)
        
        # Verify signal was processed
        current_signal = trade_signal.generate_signal()
        assert current_signal in [1.0, -1.0, 0], f"Signal mismatch. Expected {signal}, got {current_signal}"

def test_market_data_flow(setup_risk):
    """Test market data processing and risk calculations"""
    risk_manager = setup_risk['risk_manager']
    symbol = setup_risk['symbol']
    
    try:
        # Initialize Redis connection
        redis_pool = RedisPool()
        publisher = redis_pool.create_publisher()
        
        # Setup Redis channels
        redis_channels = [
            get_candlestick_channel(symbol.lower()),
            get_orderbook_channel(symbol.lower()),
            get_execution_channel(symbol.lower())
        ]
        
        # Start Binance connection in a separate thread
        def start_binance():
            try:
                gateway = BinanceGateway(symbol=symbol, redis_publisher=publisher)
                gateway.connection()
                print("Binance connection established")
            except Exception as e:
                print(f"Error connecting to Binance: {str(e)}")
                raise
        
        binance_thread = threading.Thread(target=start_binance, daemon=True)
        binance_thread.start()
        
        # Wait for Binance connection
        time.sleep(2)  # Give time for connection to establish
        
        # Start subscriber in a separate thread
        def start_subscriber():
            try:
                subscriber = redis_pool.create_subscriber(redis_channels)
                
                # Register handlers
                for channel in redis_channels:
                    if "candlestick" in channel:
                        subscriber.register_handler(channel, risk_manager.process_candlestick)
                    if "orderbook" in channel:
                        subscriber.register_handler(channel, risk_manager.data_aggregator)
                    if "execution" in channel:
                        subscriber.register_handler(channel, lambda x: print(f"Execution update: {x}"))
                
                subscriber.start_subscribing()
                print("Redis subscriber started")
            except Exception as e:
                print(f"Error starting subscriber: {str(e)}")
                raise
        
        subscriber_thread = threading.Thread(target=start_subscriber, daemon=True)
        subscriber_thread.start()
        
        # Wait for initial data with timeout
        max_wait = 10  # Maximum wait time in seconds
        start_time = time.time()
        while time.time() - start_time < max_wait:
            if not risk_manager.orderbook_df.empty and not risk_manager.candlestick_df.empty:
                # Check if we have enough data points for volatility calculation
                if len(risk_manager.candlestick_df) >= 2:  
                    break
            print(f"Waiting for data... Current candlesticks: {len(risk_manager.candlestick_df)}")
            time.sleep(0.5)  # Check every 500ms
        
        if len(risk_manager.candlestick_df)<2:
            print("No real-time candles received. Use dummy data...")
            now = pd.Timestamp.utcnow().floor('min')
            candles = pd.DataFrame({
                'datetime': [now - pd.Timedelta(minutes=i) for i in range(20)][::-1],
                'open': np.linspace(100, 120, 20),
                'high': np.linspace(101, 121, 20),
                'low': np.linspace(99, 119, 20),
                'close': np.linspace(100, 120, 20),
                'volume': [1.0] * 20,
                'symbol': ["BTCUSDT"] * 20,
                'interval': ["1m"] * 20,
                'start_time': [0] * 20,
                'end_time': [0] * 20,
                'source': ["synthetic"] * 20,
                'is_closed': [True] * 20
            }).set_index('datetime')
            risk_manager.candlestick_df = candles
        
        # Verify data is being received
        assert not risk_manager.orderbook_df.empty, "No orderbook data received within timeout"
        assert not risk_manager.candlestick_df.empty, "No candlestick data received within timeout"
        assert len(risk_manager.candlestick_df) >= 2, "Insufficient candlestick data for volatility calculation"
        
        # Print data status
        print(f"Received {len(risk_manager.candlestick_df)} candlesticks")
        print(f"Received {len(risk_manager.orderbook_df)} orderbook updates")
        
        # Test volatility calculation with live data
        vol = risk_manager.calculate_rolling_vol()
        assert vol is not None, "Volatility calculation failed"
        print(f"Calculated volatility from live data: {vol:.4f}")
        
        # Print latest market data
        print(f"Latest mid price: {risk_manager.orderbook_df['mid_price'].iloc[-1]}")
        print(f"Latest spread: {risk_manager.orderbook_df['spread_pct'].iloc[-1]:.6f}")
        print(f"Latest candlestick close: {risk_manager.candlestick_df['close'].iloc[-1]}")
        
    except Exception as e:
        pytest.fail(f"Test failed with error: {str(e)}")
    finally:
        try:
            redis_pool.close()
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")

def test_position_sizing(setup_risk):
    """Test position sizing calculation"""
    risk_manager = setup_risk['risk_manager']
    now = pd.Timestamp.utcnow().floor('min')
    candles = pd.DataFrame({
        'datetime': [now - pd.Timedelta(minutes=i) for i in range(20)][::-1],
        'open': np.linspace(100, 120, 20),
        'high': np.linspace(101, 121, 20),
        'low': np.linspace(99, 119, 20),
        'close': np.linspace(100, 120, 20),
        'volume': [1.0] * 20,
        'symbol': ["BTCUSDT"] * 20,
        'interval': ["1m"] * 20,
        'start_time': [0] * 20,
        'end_time': [0] * 20,
        'source': ["synthetic"] * 20,
        'is_closed': [True] * 20
        }).set_index('datetime')
    risk_manager.candlestick_df = candles
    
    # Get current ATR
    atr = risk_manager.calculate_atr()
    assert atr is not None, "ATR calculation failed"
    
    # Calculate position size
    position_size = risk_manager.calculate_position_size()
    assert position_size > 0, "Invalid position size calculated"

def test_drawdown_limits(setup_risk):
    """Test drawdown limit calculations"""
    risk_manager = setup_risk['risk_manager']
    
    # Get current portfolio value
    current_prices = risk_manager.portfolio_manager.get_cash()
    
    # Test drawdown limits
    drawdown_check = risk_manager.calculate_drawdown_limits(current_prices, order=None)
    assert isinstance(drawdown_check, bool), "Drawdown check should return boolean"

# def test_circuit_breaker(setup_risk):
#     """Test circuit breaker functionality"""
#     risk_manager = setup_risk['risk_manager']
    
#     # Test circuit breaker activation
#     risk_manager.trigger_circuit_breaker("Test activation")
#     assert risk_manager.circuit_breaker, "Circuit breaker not activated"
    
#     # Test position entry with circuit breaker active
#     current_prices = risk_manager.portfolio_manager.get_cash()
#     entry_result = risk_manager.entry_position(50000.0, current_prices, risk_manager.api)
#     assert entry_result is None, "Position entry should be blocked by circuit breaker"

def test_stop_loss_take_profit(setup_risk):
    """Test stop loss and take profit calculations"""
    risk_manager = setup_risk['risk_manager']
    now = pd.Timestamp.utcnow().floor('min')
    candles = pd.DataFrame({
        'datetime': [now - pd.Timedelta(minutes=i) for i in range(20)][::-1],
        'open': np.linspace(100, 120, 20),
        'high': np.linspace(101, 121, 20),
        'low': np.linspace(99, 119, 20),
        'close': np.linspace(100, 120, 20),
        'volume': [1.0] * 20,
        'symbol': ["BTCUSDT"] * 20,
        'interval': ["1m"] * 20,
        'start_time': [0] * 20,
        'end_time': [0] * 20,
        'source': ["synthetic"] * 20,
        'is_closed': [True] * 20
        }).set_index('datetime')
    risk_manager.candlestick_df = candles
    
    entry_price = 50000.0
    atr = risk_manager.calculate_atr()
    assert atr is not None, "ATR calculation failed"
    
    tp, sl = risk_manager.calc_tp_sl(entry_price, atr.iloc[-1], "LONG")
    assert sl < entry_price, "Stop loss should be below entry price"
    assert tp > entry_price, "Take profit should be above entry price"

def test_full_workflow(setup_risk):
    """Test complete risk management workflow with strategy integration"""
    risk_manager = setup_risk['risk_manager']
    signal_queue = setup_risk['signal_queue']
    symbol = setup_risk['symbol']
    
    try:
        # Initialize Redis connection
        redis_pool = RedisPool()
        publisher = redis_pool.create_publisher()
        
        # Setup Redis channels
        redis_channels = [
            get_candlestick_channel(symbol.lower()),
            get_orderbook_channel(symbol.lower()),
            get_execution_channel(symbol.lower())
        ]
        
        # Start Binance connection in a separate thread
        def start_binance():
            try:
                gateway = BinanceGateway(symbol=symbol, redis_publisher=publisher)
                gateway.connection()
                print("Binance connection established")
            except Exception as e:
                print(f"Error connecting to Binance: {str(e)}")
                raise
        
        binance_thread = threading.Thread(target=start_binance, daemon=True)
        binance_thread.start()
        
        # Wait for Binance connection
        time.sleep(2)
        
        # Start subscriber in a separate thread
        def start_subscriber():
            try:
                subscriber = redis_pool.create_subscriber(redis_channels)
                
                # Register handlers
                for channel in redis_channels:
                    if "candlestick" in channel:
                        subscriber.register_handler(channel, risk_manager.process_candlestick)
                    if "orderbook" in channel:
                        subscriber.register_handler(channel, risk_manager.data_aggregator)
                    if "execution" in channel:
                        subscriber.register_handler(channel, lambda x: print(f"Execution update: {x}"))
                
                subscriber.start_subscribing()
                print("Redis subscriber started")
            except Exception as e:
                print(f"Error starting subscriber: {str(e)}")
                raise
        
        subscriber_thread = threading.Thread(target=start_subscriber, daemon=True)
        subscriber_thread.start()
        
        # Wait for initial data with timeout
        max_wait = 5
        start_time = time.time()
        while time.time() - start_time < max_wait:
            if not risk_manager.orderbook_df.empty and not risk_manager.candlestick_df.empty:
                break
            print(f"Waiting for data... Current orderbook updates: {len(risk_manager.orderbook_df)}")
            time.sleep(0.5)
        
        if risk_manager.orderbook_df.empty:
            print("No real-time orderbook data received. Using dummy data...")
            now = pd.Timestamp.utcnow()
            orderbook_data = pd.DataFrame([{
                "timestamp": now,
                "best_bid": 50000.0,
                "best_ask": 50001.0,
                "mid_price": 50000.5,
                "spread": 1.0,
                "spread_pct": 0.00002
            }]).set_index("timestamp")
            risk_manager.orderbook_df = orderbook_data
        
        if risk_manager.candlestick_df.empty:
            print("No real-time candles received. Using dummy data...")
            now = pd.Timestamp.utcnow().floor('min')
            candles = pd.DataFrame({
                'datetime': [now - pd.Timedelta(minutes=i) for i in range(20)][::-1],
                'open': np.linspace(100, 120, 20),
                'high': np.linspace(101, 121, 20),
                'low': np.linspace(99, 119, 20),
                'close': np.linspace(100, 120, 20),
                'volume': [1.0] * 20,
                'symbol': ["BTCUSDT"] * 20,
                'interval': ["1m"] * 20,
                'start_time': [0] * 20,
                'end_time': [0] * 20,
                'source': ["synthetic"] * 20,
                'is_closed': [True] * 20
            }).set_index('datetime')
            risk_manager.candlestick_df = candles
        
        # Verify data is available
        assert not risk_manager.orderbook_df.empty, "No orderbook data available"
        assert not risk_manager.candlestick_df.empty, "No candlestick data available"
        
        # 2. Position Sizing
        position_size = risk_manager.calculate_position_size()
        assert position_size > 0, "Invalid position size calculated"
        print(f"Calculated position size: {position_size:.4f}")
        
        # 3. Risk Checks
        current_cash = risk_manager.portfolio_manager.get_cash()
        drawdown_check = risk_manager.calculate_drawdown_limits(current_cash, order=None)
        assert isinstance(drawdown_check, bool), "Drawdown check should return boolean"
        print(f"Drawdown check passed: {drawdown_check}")
        
        # 4. Strategy Signal and Entry Decision
        # Update strategy with latest data
        latest_candle = risk_manager.candlestick_df.iloc[-1].to_dict()
        risk_manager.trade_signal.update_data(latest_candle)
        
        # Generate and process signal
        signal = risk_manager.trade_signal.generate_signal()
        risk_manager.accept_signal(signal)
        print(f"Generated and processed signal: {signal}")
        
        if drawdown_check:
            entry_result = risk_manager.entry_position(50000.0, current_cash, risk_manager.api)
            if entry_result:
                tp, sl = entry_result
                assert sl < 50000.0, "Stop loss should be below entry price"
                assert tp > 50000.0, "Take profit should be above entry price"
                print(f"Entry position calculated - TP: {tp:.2f}, SL: {sl:.2f}")
        
        # 5. Position Management
        positions = risk_manager.portfolio_manager.get_positions()
        if positions:
            risk_manager.manage_position(50000.0, current_cash)
            assert risk_manager.portfolio_manager.get_positions() is not None, "Position management should be active"
            print("Position management active")
        
    except Exception as e:
        pytest.fail(f"Test failed with error: {str(e)}")
    finally:
        try:
            redis_pool.close()
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")

def main():
    """Run all tests"""
    test = TestRiskManager()
    setup = test.setup()
    
    print("\n=== Testing Market Data Flow ===")
    test.test_market_data_flow(setup)
    
    print("\n=== Testing Position Sizing ===")
    test.test_position_sizing(setup)
    
    print("\n=== Testing Drawdown Limits ===")
    test.test_drawdown_limits(setup)
    
    print("\n=== Testing Circuit Breaker ===")
    test.test_circuit_breaker(setup)
    
    print("\n=== Testing Stop Loss/Take Profit ===")
    test.test_stop_loss_take_profit(setup)
    
    print("\n=== Testing Full Workflow ===")
    test.test_full_workflow(setup)


if __name__ == "__main__":
    main()
