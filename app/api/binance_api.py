## Binance Gateway Implementation
# WebSocket to fetch live data
# Current set up - test funcs using binance testnet 

# TODO: refer to binance gateway template and store data in redis + try to fetch the data for all other modules 

import pandas as pd
from binance import Client

from app.common.interface_order import Side
from app.utils.config import settings
from app.utils.logger import setup_logger, main_logger as logger

from app.common.interface_message import RedisMessage
from app.common.interface_api import FuturesAccountBalance, FuturesAPIOrder, FuturesPositionResponse, FuturesKlineBulk, FuturesClosingPrices
from app.common.interface_order import OrderType, Side
import asyncio
from queue import Queue
from app.services import RedisPool
import threading
import msgspec
import multiprocessing as mp



class BinanceApi:
    def __init__(
            self, symbol:str, 
            api_key=None, 
            api_secret=None, 
            name:str = "", 
            testnet=True,
            redis_pool : RedisPool = None,
            log_queue : mp.Queue = None
        ):
        self._api_key = api_key or settings.BINANCE_TEST_API_KEY
        self._api_secret = api_secret or settings.BINANCE_TEST_API_SECRET
        self._exchange_name = name 
        self._symbol = symbol.lower() # symbols from binance websocket are in lower case (default)
        self._testnet = testnet
        self.redis_pool = redis_pool

        self._api_logger = setup_logger(
                    logger_name="api",
                    logger_path="./logs/api",
                    log_type="api",
                    enable_console=False,
                    queue=log_queue
                    )

        # binance async client
        self._client = Client(self._api_key, self._api_secret, testnet=testnet)
        self._Channels = [
            "API@orders", 
            "API@account_balance",
            "API@positions",
            "API@close",
            "API@ohlcv"
        ]

    """
    Place market order for futures trading
    """
    def place_market_order(self, symbol: str, side: str, qty: float) -> bool:
        try:
            new_qty = round(qty, 3)
            # new_price = round(, 6)
            logger.info(f"Trying to place market order in api: {symbol} , side: {side}, qty: {new_qty}")
            self.check_client_exist()

            # ROUND TO 8 Decimal places:

            order_response = self._client.futures_create_order(symbol=symbol.upper(),
                                        type=Client.FUTURE_ORDER_TYPE_MARKET,
                                        side=side,
                                        quantity=new_qty)
            logger.info(f"Order submitted: {order_response}")
            return order_response
        except Exception as e:
            logger.error("Failed to place order: {}".format(e))
            return False
            
    """
    Place a limit order for FUTURES trading
    """
    def place_limit_order(self, side: Side, price, quantity, tif='IOC', symbol=""):
        if not symbol : 
            symbol = self._symbol.upper()
        try:
            self.check_client_exist()
            order_response = self._client.futures_create_order(symbol=symbol,
                                              side=side.name,
                                              type=Client.FUTURE_ORDER_TYPE_LIMIT,
                                              price=price,
                                              quantity=quantity,
                                              timeInForce=tif)
            logger.info(f"Order submitted: {order_response}")
            return order_response
        except Exception as e:
            logger.error("Failed to place order: {}".format(e))
            res = {
                "status": "FAILED",
                "errorMsg": str(e),
            }
            return res

    def place_stop_loss(self, side: Side, quantity: float, price: float, symbol="") -> bool:
        if not symbol : 
            symbol = self._symbol.upper()
        try: 
            self.check_client_exist()
            order_response = self._client.futures_create_order(
                                              symbol=self._symbol.upper(),
                                              side=Client.SIDE_SELL,
                                              type=Client.FUTURE_ORDER_TYPE_STOP_MARKET,
                                              stopPrice=price,
                                              closePosition=True,
                                              quantity=quantity,
                                              timeInForce='GTC')
            logger.info(f"Stop loss order placed: {order_response}")
            return order_response
        except Exception as e:
            self._api_logger.warning("Failed to create stop loss order: {}".format(e))
            return False
        
    def place_take_profit(self, side: Side, quantity: float, price: float, symbol="") -> bool:
        if not symbol : 
            symbol = self._symbol.upper()
        try:
            self.check_client_exist()
            order_response = self._client.futures_create_order(
                                              symbol=symbol,
                                              side=Client.SIDE_SELL,
                                              type=Client.FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
                                              stopPrice=price,
                                              closePosition=True,
                                              quantity=quantity,
                                              timeInForce='GTC')
            logger.info(f"Take profit order placed: {order_response}")
            return order_response
        except Exception as e:
            self._api_logger.warning("Failed to create take profit order: {}".format(e))
            return False
            
    def cancel_order(self, symbol:str, order_id: int) -> bool:
        try:
            self.check_client_exist()
            order_response = self._client.futures_cancel_order(
                                            symbol=symbol.upper(),
                                            orderId=order_id)
            logger.info(f"Order cancelled: {order_response}")
            return order_response
        except Exception as e:
            self._api_logger.warning("Failed to cancel order: {}, {}".format(e))
            return False
        
    def cancel_open_orders(self, symbol: str) -> bool:
        try:
            self.check_client_exist()
            order_response = self._client.futures_cancel_all_open_orders(symbol=symbol.upper())
            return order_response
        except Exception as e:
            self._api_logger.warning("Failed to cancel all open orders: {}".format(e))
            return False

    def check_client_exist(self):
        if self._client is None:
            logger.info("Trying to instantiate client now")
            self._client = Client(self._api_key, self._api_secret, testnet=True)

    def get_account_balance(self) -> dict:
        try:
            self.check_client_exist()
            return self._client.futures_account_balance()
        except Exception as e:
            error_msg = f"Failed to retrieve account balance: {e}"
            self._api_logger.warning(error_msg)
            return {"errorMsg": error_msg}
        
    def get_open_orders(self, symbol: str) -> list:
        try:
            self.check_client_exist()
            return self._client.futures_get_open_orders(symbol=symbol.upper())
        except Exception as e:
            error_msg = f"Failed to retrieve open orders: {e}"
            self._api_logger.warning(error_msg)
            return {"errorMsg": error_msg}

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
            self._api_logger.warning(error_msg)
            return {"errorMsg": error_msg}


    """ 
    Get Candle Data
    """
    def get_ohlcv(self, symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_1MINUTE, limit=200):
        candles = self._client.get_klines(symbol=symbol, interval=interval, limit=limit)
        candles_data = FuturesKlineBulk.from_list(candles)
        # Convert to Polars DataFrame
        return candles_data

    def get_close_prices_df(self, symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_1MINUTE, limit=200):
        df = self.get_ohlcv(symbol, interval, limit)
        return df[['timestamp', 'close']]
    

    async def accept_message(self) :
        order_decoder = msgspec.msgpack.Decoder(FuturesAPIOrder)

        while True :
            msg = await self.get_from_queue(self._subscriber_queue)
            if msg.topic == "account_balance" :
                try : 
                    acc_balance = self.get_account_balance()
                    if isinstance(acc_balance, dict) : 
                        payload = FuturesAccountBalance(errMsg=acc_balance["errMsg"])
                    else : 
                        payload = FuturesAccountBalance(acc=acc_balance)
                    self._publisher.publish_sync(channel="Response", data=payload, topic="response", correlation_id=msg.correlation_id, set_key=False)
                except Exception as e : 
                    print("Failure retrieving account balance, " + str(e))

            elif msg.topic == "place_order" :
                order_decoded = order_decoder.decode(msg.value)
                if order_decoded.order_type == OrderType.Limit : 
                    self.place_limit_order(symbol=order_decoded.symbol, side=order_decoded.side, price=order_decoded.price, quantity=order_decoded.qty)
                elif order_decoded.order_type == OrderType.Market :
                    self.place_market_order(symbol=order_decoded.symbol, side=order_decoded.side, qty=order_decoded.qty)
                elif order_decoded.order_type == OrderType.StopMarket : 
                    self.place_stop_loss(symbol=order_decoded.symbol, side=order_decoded.side, qty=order_decoded.qty)
                elif order_decoded.order_type == OrderType.TakeProfit : 
                    self.place_take_profit(symbol=order_decoded.symbol, side=order_decoded.side, qty=order_decoded.qty)

            elif msg.topic == "positions" :
                position = self.get_current_position()
                if isinstance(position, dict) : 
                    payload = FuturesPositionResponse(errMsg=position["errMsg"])
                else :
                    payload = FuturesPositionResponse.from_list(acc=acc_balance)
                    self._publisher.publish_sync(channel="Response", data=payload, topic="response", correlation_id=msg.correlation_id, set_key=False)

            elif msg.topic == "ohlcv" : 
                candles = self.get_ohlcv()
                self._publisher.publish_sync(channel="Response", data=candles, topic="response", correlation_id=msg.correlation_id)

            elif msg.topic == "close" : 
                candles = self.get_ohlcv()
                close_prices = FuturesClosingPrices.from_bulk(candles)
                self._publisher.publish_sync(channel="Response", data=close_prices, topic="response", correlation_id=msg.correlation_id)


    async def get_from_queue(self, q: Queue) -> RedisMessage :
        loop = self._loop
        return await loop.run_in_executor(None, q.get)
    
    def start(self) :
        self._loop = asyncio.new_event_loop()
        
        # Start the loop in a background thread FIRST
        t = threading.Thread(target=self._loop.run_forever, daemon=True)
        t.start()

        # Create the queue
        self._subscriber_queue = Queue()

        # Now that the loop is running, safely submit coroutines
        asyncio.run_coroutine_threadsafe(self.accept_message(), loop=self._loop)

        # Initialize Redis pub/sub
        self._publisher = self.redis_pool.create_publisher()
        self._subscriber = self.redis_pool.create_subscriber(self._Channels, q=self._subscriber_queue)

        # Start the async subscriber
        self._subscriber.start_subscribing()