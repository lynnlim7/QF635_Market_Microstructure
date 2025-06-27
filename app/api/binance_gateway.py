## Binance Gateway Implementation
# WebSocket to fetch live data
# Current set up - test funcs using binance testnet 

# TODO: refer to binance gateway template and store data in redis + try to fetch the data for all other modules 

import asyncio
import json
import os
from threading import Thread
import time

import schedule
import websockets
import websockets.exceptions

from binance import AsyncClient, BinanceSocketManager, Client
from binance.ws.depthcache import FuturesDepthCacheManager

from app.common.interface_book import VenueOrderBook, PriceLevel, OrderBook, KlineEvent
from app.common.interface_order import OrderEvent
from app.common.order_event_update import OrderEventUpdate
from app.services import RedisPool
from app.utils.config import settings
from app.utils.func import get_candlestick_channel, get_execution_channel, get_orderbook_channel
from app.utils.logger import setup_logger
from app.utils.logger import main_logger as logger
import multiprocessing as mp

# initialize redis pub
# redis_publisher = RedisPublisher(prefix="market_data")


"""
Gateway for websocket connections
"""
class BinanceGateway:
    def __init__(self, symbol:str, api_key=None, api_secret=None, name:str = "", testnet=True, redis_pool : RedisPool =None, log_queue : mp.Queue = None):
        os.makedirs("./logs/market", exist_ok=True)
        os.makedirs("./logs/orders", exist_ok=True)
        
        self._api_key = api_key or settings.BINANCE_TEST_API_KEY
        self._api_secret = api_secret or settings.BINANCE_TEST_API_SECRET
        self._exchange_name = name 
        self._symbol = symbol.lower() # symbols from binance websocket are in lower case (default)
        self._testnet = testnet
        
        self._orderbook_logger = setup_logger(
                    logger_name="orderbook", 
                    logger_path="./logs/market",
                    log_type="orderbook", 
                    enable_console=False,
                    queue=log_queue,
                    )
                
        self._kline_logger = setup_logger(
                    logger_name="kline", 
                    logger_path="./logs/market",
                    log_type="kline",
                    enable_console=False,
                    queue=log_queue,
                    )

        self._execution_logger = setup_logger(
                    logger_name="execution",
                    logger_path="./logs/market",
                    log_type="execution",
                    enable_console=False,
                    queue=log_queue,
                    )

        # binance async client
        self._async_client = None

        # futures depth cache
        self._depth_cache = None
        self._dcm = None  # depth cache, which implements the logic to manage a local order book
        self._dws = None  # depth async WebSocket session

        # binance main net 
        self.market_data_async_client = None

        # binance socket managers
        self.binance_socket_manager = None
        self.redis_pool = redis_pool

        # callbacks
        self._depth_callbacks = []
        self._kline_callbacks = []
        self._execution_callbacks = []

    def _extend_listen_key(self):
        self._orderbook_logger.info("Extending listen key")
        if self._async_client and self._listen_key:
            asyncio.run_coroutine_threadsafe(
                self._async_client.futures_stream_keepalive(self._listen_key),
                self._loop
            )

    # an internal method to reconnect websocket
    async def _reconnect_ws(self):
        self._orderbook_logger.info("Reconnecting websocket")
        # main net
        self.market_data_async_client = await AsyncClient.create()

        # test net
        self._async_client = await AsyncClient.create(
            api_key = self._api_key, 
            api_secret = self._api_secret, 
            testnet=True)

        self.binance_socket_manager = BinanceSocketManager(self.market_data_async_client)

    # an internal method to runs tasks in parallel
    def _run_async_tasks(self):
        """ Run the following tasks concurrently in the current thread """
        self._loop.create_task(self._listen_futures_depth_forever())
        self._loop.create_task(self._listen_execution_forever())
        self._loop.create_task(self._listen_kline_forever())
        self._loop.create_task(self._keepalive_loop())
        self._loop.run_forever()

    async def _listen_futures_depth_forever(self):
        self._orderbook_logger.info("Subscribing to depth events")
        while True:
            if not self._dws:
                self._orderbook_logger.info("depth socket not connected, reconnecting")
                # current stream url is this: 'wss://stream.binancefuture.com/'
                self._dcm = FuturesDepthCacheManager(self._async_client, symbol=self._symbol)
                self._dws = await self._dcm.__aenter__()

            # wait for depth update
            try:
                self._depth_cache = await self._dws.recv()

                # generating orderbook object
                bids = [PriceLevel(price=p, size=s) for (p, s) in self._depth_cache.get_bids()[:5]]
                asks = [PriceLevel(price=p, size=s) for (p, s) in self._depth_cache.get_asks()[:5]]
                order_book = OrderBook(timestamp=self._depth_cache.update_time, contract_name=self._symbol, bids=bids, asks=asks)

                orderbook_channel = get_orderbook_channel(self._symbol)
                self._publisher.publish_sync(channel=orderbook_channel, data=order_book, topic="order_book_update", set_key=True)
                self._orderbook_logger.info(f"{order_book.contract_name} | best bid: {order_book.bids[0]} | best ask: {order_book.asks[0]}")

                if self._depth_callbacks:
                    # notify callbacks
                    for _callback in self._depth_callbacks:
                        _callback(self._depth_cache)
            except Exception as e:
                self._orderbook_logger.exception('encountered issue in depth processing')
                # reset socket and reconnect
                self._dws = None
                await self._reconnect_ws()

    # an internal async method to listen to user data stream
    async def _listen_execution_forever(self):
        self._execution_logger.info("Subscribing to user data events")
        self._listen_key = await self._async_client.futures_stream_get_listen_key()
        if self._testnet:
            url = 'wss://stream.binancefuture.com/ws/' + self._listen_key
        else:
            url = 'wss://fstream.binance.com/ws/' + self._listen_key

        async with websockets.connect(url) as ws :
            try:
                async for _message in ws:
                    _data = json.loads(_message)
                    update_type = _data.get('e')

                    if update_type == 'ORDER_TRADE_UPDATE':
                        try:
                            evt = OrderEventUpdate.from_user_stream(_data)
                            self._execution_logger.info(f"Order Event: {evt}")
                            execution_channel = get_execution_channel(self._symbol)
                            self.publisher.publish(execution_channel, evt.to_dict())
                        except ValueError as exc:
                            self._execution_logger.error("Bad ORDER_TRADE_UPDATE: %s", exc)
                            return

                        if self._execution_callbacks:
                            for _callback in self._execution_callbacks:
                                _callback(evt)
                    else:
                        logger.info(f"random msg: {_data}")
            except websockets.exceptions.ConnectionClosed:
                logger.warn("WebSocket connection closed")

    async def _listen_kline_forever(self):
        self._kline_logger.info("Subscribing to kline stream")
        # ws url: 'wss://fstream.binance.com/'
        kline_socket = self.binance_socket_manager.kline_futures_socket(symbol=self._symbol, interval=Client.KLINE_INTERVAL_1MINUTE)
        self._kline_logger.info(f"Created kline socket for {self._symbol}")

        # async manager to make sure ws is connected and opened
        async with kline_socket as stream:
            self._kline_logger.info("Kline socket connection established")
            while True:
                try:
                    message = await stream.recv()
                    self._kline_logger.info(f"Raw kline message received: {message}")
                    k = message['k']
                    self._kline_logger.info(f"Processing kline data: {k}")

                    candles_dict = KlineEvent(
                        symbol=message['ps'],
                        interval=k['i'],
                        open=float(k['o']),
                        close=float(k['c']),
                        high=float(k['h']),
                        low=float(k['l']),
                        volume=float(k['v']),
                        is_closed=k['x'],
                        start_time=k['t'],
                        end_time=k['T'],
                        source="candlestick"
                    )

                    candlestick_channel = get_candlestick_channel(self._symbol)
                    self._kline_logger.info(f"Publishing to channel {candlestick_channel}: {candles_dict}")
                    self._publisher.publish_sync(candlestick_channel, candles_dict, topic="candlestick", set_key=True)
                    self._kline_logger.info(f"Successfully published to {candlestick_channel}")
                except Exception as e:
                    self._kline_logger.exception(f"Encountered issue in kline stream processing: {str(e)}")
                    # Add a small delay before retrying
                    await asyncio.sleep(1)

    """ 
    Register a depth callback function that takes one argument: (book: VenueOrderBook) 
    """
    def register_depth_callback(self, callback):
        self._depth_callbacks.append(callback)

    """ 
    Register an execution callback function that takes one argument, an order event: (event: OrderEvent) 
    """
    def register_execution_callback(self, callback):
        self._execution_callbacks.append(callback)

    def register_kline_callback(self, callback):
        self._kline_callbacks.append(callback)

    def start(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # 1. Connect and initialize Binance clients
        self._loop.run_until_complete(self._reconnect_ws())

        # 2. Create publisher
        self._publisher = self.redis_pool.create_publisher()

        # 3. Start background thread for asyncio tasks
        self._loop_thread = Thread(target=self._run_async_tasks, daemon=True)
        self._loop_thread.start()

    async def _keepalive_loop(self):
        while True:
            try:
                await self._async_client.futures_stream_keepalive(self._listen_key)
                self._orderbook_logger.info("Extended listen key")
            except Exception as e:
                self._orderbook_logger.error(f"Keepalive failed: {e}")
            await asyncio.sleep(15 * 60)

# # callback on order book update
# def on_orderbook(order_book: VenueOrderBook):
#     self._orderbook_logger.info("Receive order book: {}".format(order_book))

# # callback on execution update
# def on_execution(order_event: OrderEventUpdate):
#     self._execution_logger.info("Receive poll: {}".format(order_event))

# def on_kline(order_event: OrderEvent):
#     self._kline_logger.info("Receive kline: {}".format(order_event))


if __name__ == '__main__':
    # create a binance gateway object
    redis_pool = RedisPool()
    redis_publisher = redis_pool.create_publisher()
    binance_gateway = BinanceGateway('BTCUSDT', redis_publisher=redis_publisher)
    # register callbacks
    binance_gateway.register_depth_callback(on_orderbook)
    binance_gateway.register_execution_callback(on_execution)
    binance_gateway.register_kline_callback(on_kline)