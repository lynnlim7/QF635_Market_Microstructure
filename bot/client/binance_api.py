import logging

from binance.client import Client

from bot.utils.logger import setup_logger


# migrate BinanceAPITester over with more data and for logging
class BinanceApi:
    def __init__(self):
        # no need keys if just using the account
        self.client = Client()

        self.market_logger = setup_logger(
            logger_name="binance_market",
            logger_path="./logs/market",
            level = logging.INFO,
            log_type="market",
            max_bytes=50*1024*1024
        )