import logging
import os
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException
from datetime import datetime
import time

# Import your logger setup
from bot.interfaces.logger import setup_logger

# Load environment variables
load_dotenv()

class BinanceAPITester:
    def __init__(self):
        # Initialize loggers
        self.market_logger = setup_logger(
            logger_name="binance_market",
            logger_path="./logs/market",
            level = logging.INFO,
            log_type="market",
            max_bytes=50*1024*1024
        )
        os.environ["WRITE_LOG"] = "TRUE"
        self.order_logger = setup_logger(
            logger_name="binance_orders",
            logger_path="./logs/orders",
            level = logging.INFO,
            log_type="order",
            rotation_int="midnight"
        )
        os.environ["TIMED_LOG"] = "FALSE"
        self.error_logger = setup_logger(
            logger_name="binance_errors",
            logger_path="./logs/errors",
            level = logging.INFO,
            log_type="error",
            max_bytes=10*1024*1024
        )
        
        # Initialize Binance client
        self.client = Client(
            os.getenv('BINANCE_API_KEY'),
            os.getenv('BINANCE_API_SECRET')
        )

    def test_market_data(self):
        """Test market data logging"""
        try:
            self.market_logger.info("Fetching market data...")
            
            # Get BTC/USDT ticker
            ticker = self.client.get_symbol_ticker(symbol="BTCUSDT")
            self.market_logger.info(f"BTC/USDT Price: {ticker['price']}")
            
            # Get order book
            depth = self.client.get_order_book(symbol='BTCUSDT', limit=5)
            self.market_logger.info(f"Order Book Depth: {depth}")
            
        except BinanceAPIException as e:
            self.error_logger.error(f"Market data error: {str(e)}")

    def test_order_operations(self):
        """Test order operations logging"""
        try:
            self.order_logger.info("Testing order operations...")
            
            # Get account information
            account = self.client.get_account()
            self.order_logger.info(f"Account Status: {account['accountType']}")
            
            # Get open orders
            orders = self.client.get_open_orders(symbol='BTCUSDT')
            self.order_logger.info(f"Open Orders: {orders}")
            
        except BinanceAPIException as e:
            self.error_logger.error(f"Order operation error: {str(e)}")

    def test_error_handling(self):
        """Test error logging"""
        try:
            # Intentionally cause an error
            self.client.get_order(symbol='BTCUSDT', orderId='invalid')
        except BinanceAPIException as e:
            self.error_logger.error(
                f"Error occurred: {str(e)}",
                exc_info=True  # Include full stack trace
            )

    def run_tests(self):
        """Run all tests"""
        self.market_logger.info("Starting Binance API tests")
        
        # Test market data
        self.test_market_data()
        
        # Test order operations
        self.test_order_operations()
        
        # Test error handling
        self.test_error_handling()
        
        self.market_logger.info("Completed Binance API tests")

if __name__ == "__main__":
    # Create logs directory if it doesn't exist
    os.makedirs("./logs/market", exist_ok=True)
    os.makedirs("./logs/orders", exist_ok=True)
    os.makedirs("./logs/errors", exist_ok=True)
    
    # Run tests
    tester = BinanceAPITester()
    tester.run_tests()