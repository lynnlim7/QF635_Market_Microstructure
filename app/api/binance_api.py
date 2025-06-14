## Binance Gateway Implementation
# WebSocket to fetch live data
# Current set up - test funcs using binance testnet 

# TODO: refer to binance gateway template and store data in redis + try to fetch the data for all other modules 

import pandas as pd
from binance import Client

from app.common.interface_order import Side
from app.utils.config import settings
from app.utils.logger import setup_logger

api_logger = setup_logger(
            logger_name="api",
            logger_path="./logs/api",
            log_type="api",
            enable_console=False
            )

class BinanceApi:
    def __init__(self, symbol:str, api_key=None, api_secret=None, name:str = "", testnet=True):
        self._api_key = api_key or settings.BINANCE_TEST_API_KEY
        self._api_secret = api_secret or settings.BINANCE_TEST_API_SECRET
        self._exchange_name = name 
        self._symbol = symbol.lower() # symbols from binance websocket are in lower case (default)
        self._testnet = testnet

        # binance async client
        self._client = Client(self._api_key, self._api_secret, testnet=testnet)

    """
    Place market order for futures trading
    """
    def place_market_order(self, quantity) -> bool:
        try:
            self.check_client_exist()
            order_response = self._client.futures_create_order(symbol=self._symbol.upper(),
                                              side=Client.SIDE_BUY,
                                              type=Client.ORDER_TYPE_MARKET,
                                              quantity=quantity)
            api_logger.info(f"Order submitted: {order_response}")
            return order_response
        except Exception as e:
            api_logger.error("Failed to place order: {}".format(e))
            return False
            
    """
    Place a limit order for FUTURES trading
    """
    def place_limit_order(self, side: Side, price, quantity, tif='IOC') -> bool:
        try:
            self.check_client_exist()
            order_response = self._client.futures_create_order(symbol=self._symbol.upper(),
                                              side=side.name,
                                              type=Client.ORDER_TYPE_LIMIT,
                                              price=price,
                                              quantity=quantity,
                                              timeInForce=tif)
            api_logger.info(f"Order submitted: {order_response}")
            return order_response
        except Exception as e:
            api_logger.error("Failed to place order: {}".format(e))
            return False

    """
    order_id: its the client_order_id from the order creation: x-Cb7ytekJff39894ef6683781a05ad8
    """
    def cancel_order(self, order_id) -> bool:
        try:
            self.check_client_exist()
            order_response = self._client.futures_cancel_order(symbol=self._symbol.upper(), origClientOrderId=order_id)
            return order_response
        except Exception as e:
            api_logger.warning("Failed to cancel order: {}, {}".format(order_id, e))
            return False

    def check_client_exist(self):
        if self._client is None:
            self._client = Client(self._api_key, self._api_secret, testnet=True)

    """
    Get current open positions.
    URL used: 'https://testnet.binancefuture.com/fapi/v3/positionRisk'
    More Info: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3
    """
    def get_current_position(self) -> dict:
        try:
            self.check_client_exist()
            return self._client.futures_position_information()
        except Exception as e:
            error_msg = f"Failed to retrieve current position: {e}"
            api_logger.warning(error_msg)
            return {"errorMsg": error_msg}


    """ 
    Get Candle Data
    """
    def get_ohlcv(self, symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_1MINUTE, limit=200):
        candles = self._client.get_klines(symbol=symbol, interval=interval, limit=limit)

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

            
            

