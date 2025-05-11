import logging

from binance.client import Client

from bot.config import settings
from bot.utils.logger import setup_logger


# migrate BinanceAPITester over with more data and for logging
class BinanceApi:
    def __init__(self):
        print(settings.BINANCE_API_KEY)
        print(settings.BINANCE_API_SECRET)
        # no need keys if just using the account
        self.client = Client(
            api_key=settings.BINANCE_API_KEY,
            api_secret=settings.BINANCE_API_SECRET,
            testnet=True
        )


        self.market_logger = setup_logger(
            logger_name="binance_market",
            logger_path="./logs/market",
            level = logging.INFO,
            log_type="market",
            max_bytes=50*1024*1024
        )

    def get_account(self):
        info = self.client.futures_account()
        print(info)