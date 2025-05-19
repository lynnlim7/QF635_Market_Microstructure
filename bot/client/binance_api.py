import logging
import pandas as pd

from binance.client import Client

from bot.utils.config import settings
from bot.utils.logger import setup_logger


# migrate BinanceAPITester over with more data and for logging
class BinanceApi:
    def __init__(self):
        if settings.BINANCE_API_KEY:
            # no need keys if just using the account
            self.client = Client(
                api_key=settings.BINANCE_API_KEY,
                api_secret=settings.BINANCE_API_SECRET,
                testnet=True
            )
        else:
            self.client = Client(testnet=True)
        self.market_logger = setup_logger(
            logger_name="binance_market",
            logger_path="./logs/market",
            level = logging.INFO,
            log_type="market",
            max_bytes=50*1024*1024
        )


    # https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints
    def get_ohlcv(self, symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_1MINUTE, limit=200):
        candles = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)

        # Convert to Polars DataFrame
        df = pd.DataFrame(candles, columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume",
            "ignore"
        ])

        numeric_columns = ["open", "high", "low", "close", "volume",
                           "quote_asset_volume", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume"]
        df[numeric_columns] = df[numeric_columns].astype(float)
        df = df.drop(columns=['ignore'])
        return df

    def get_close_prices_df(self, symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_1MINUTE, limit=200):
        df = self.get_ohlcv(symbol, interval, limit)
        return df[['timestamp', 'close']]

