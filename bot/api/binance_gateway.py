## Binance Gateway Implementation
# WebSocket to fetch live data
# Current set up - test funcs using binance testnet 

# TODO: refer to binance gateway template and store data in redis + try to fetch the data for all other modules 

import asyncio
from binance import AsyncClient, BinanceSocketManager, Client
from bot.utils.logger import setup_logger
from bot.utils.config import settings
from bot.services.redis_pub import RedisPublisher
from bot.common.interface_book import VenueOrderBook, PriceLevel, OrderBook
from bot.common.interface_order import OrderEvent, OrderStatus, ExecutionType, Side
from bot.utils.func import get_candlestick_channel, get_execution_channel, get_orderbook_channel
import os
import time
from threading import Thread

# initialize redis pub
redis_publisher = RedisPublisher(prefix="market_data")

orderbook_logger = setup_logger(
            logger_name="orderbook", 
            logger_path="./logs/market",
            log_type="orderbook", 
            enable_console=False
            )
        
polling_logger = setup_logger(
            logger_name="polling", 
            logger_path="./logs/orders",
            log_type="polling",
            enable_console=False
            )
        
kline_logger = setup_logger(
            logger_name="kline", 
            logger_path="./logs/market",
            log_type="kline",
            enable_console=False
            )

class BinanceGateway:
    def __init__(self, symbol:str, api_key=None, api_secret=None, name:str = "", testnet=True, redis_publisher=None):
        os.makedirs("./logs/market", exist_ok=True)
        os.makedirs("./logs/orders", exist_ok=True)
        
        self._api_key = api_key or settings.BINANCE_TEST_API_KEY
        self._api_secret = api_secret or settings.BINANCE_TEST_API_SECRET
        self._exchange_name = name 
        self._symbol = symbol.lower() # symbols from binance websocket are in lower case (default)
        self._testnet = testnet
        self.publisher = redis_publisher

        # binance async client
        self._client = Client(api_key, api_secret, testnet=True)
        self._async_client = None
        self._dcm = None  # depth cache, which implements the logic to manage a local order book
        self._dws = None  # depth async WebSocket session

        # binance main net 
        self.market_data_client = None
        self.market_data_async_client = None

        # binance test net 
        self.trade_client = Client(settings.BINANCE_TEST_API_KEY, settings.BINANCE_TEST_API_SECRET)
        self.trade_client.API_URL = "https://testnet.binance.vision/api"

        # depth cache
        self._depth_cache = None

        # loop and dedicated thread to run all async concurrent tasks
        self._loop = asyncio.new_event_loop()
        self._loop_thread = Thread(target=self._run_async_tasks, daemon=True, name=name)

        # callbacks
        self._depth_callbacks = []
        self._polling_callbacks = []
        self._kline_callbacks = []

    def connection(self):
        orderbook_logger.info("Initializing connection...")
        self._loop.run_until_complete(self._reconnect_ws())
        orderbook_logger.info("Starting event loop thread...")
        self._loop_thread.start()

    # an internal method to reconnect websocket
    async def _reconnect_ws(self):
        orderbook_logger.info("Reconnecting websocket")
        # main net
        self.market_data_async_client = await AsyncClient.create()

        # test net
        self._async_client = await AsyncClient.create(
            api_key = self._api_key, 
            api_secret = self._api_secret, 
            testnet=True)

    # an internal method to runs tasks in parallel
    def _run_async_tasks(self):
        """ Run the following tasks concurrently in the current thread """
        self._loop.create_task(self._listen_depth_forever())
        self._loop.create_task(self._poll_order_updates())
        self._loop.create_task(self._listen_kline_forever())
        self._loop.run_forever()

    # an internal async method to listen to depth stream
    async def _listen_depth_forever(self):
        bsm = BinanceSocketManager(self.market_data_async_client)
        socket = bsm.depth_socket(symbol=self._symbol)
        orderbook_logger.info("Subscribing to depth stream")

        async with socket as stream:
            while True:
                # wait for depth update
                try:
                    msg = await stream.recv()
                    orderbook_dict = {
                        "symbol": self._symbol,
                        "timestamp": msg['E'],
                        "bids": msg['b'][:5],
                        "asks": msg['a'][:5],
                        "source": "orderbook"
                    }
                    orderbook_channel = get_orderbook_channel(self._symbol)
                    self.publisher.publish(orderbook_channel, orderbook_dict)
                    orderbook_logger.info(f"{orderbook_dict['symbol']} | best bid: {orderbook_dict['bids'][0]} | best ask: {orderbook_dict['asks'][0]}")

                    if self._depth_callbacks:
                        # notify callbacks
                        for _callback in self._depth_callbacks:
                            _callback(orderbook_dict)
                except Exception as e:
                    orderbook_logger.exception('Encountered issue in depth processing')
                    await asyncio.sleep(5)
            await client.close_connection()

    # testnet polling of trade orders
    async def _poll_order_updates(self):
        polling_logger.info("Polling order status")
        while True: 
            try:
                open_orders = self.trade_client.get_open_orders(symbol=self._symbol.upper())
                for order in open_orders:
                    order_status = order['status']
                    execution_dict = {
                            "symbol": order['symbol'],
                            "order_id": order['orderId'],
                            "execution_type": "Poll",
                            "order_status": order_status,
                            "side": order['side'],
                            "price": float(order['price']),
                            "quantity": float(order['quantity']),
                            "timestamp": int(time.time() * 1000),
                            "source": "execution"
                            }
                    polling_channel = get_execution_channel(self._symbol)
                    self.publisher.publish(polling_channel, execution_dict)
                    polling_logger.info(f"Poll | {execution_dict['symbol']} | order_id: {execution_dict['order_id']} | status: {order_status}")

                    # create order event 
                    if self._polling_callbacks:
                        _order_event = OrderEvent(
                            order['symbol'],
                            order['order_id'],
                            order['execution_type'],
                            order['order_status']
                        )
                        _order_event.side = Side[order['side']]
                        for _callback in self._polling_callbacks:
                                _callback(_order_event)
                await asyncio.sleep(3)
            except Exception as e:
                polling_logger.exception("Error encountered while polling updates..")
                await asyncio.sleep(5)
    
    async def _listen_kline_forever(self):
        kline_logger.info("Subscribing to kline stream")
        socket_manager = BinanceSocketManager(self.market_data_async_client)
        kline_socket = socket_manager.kline_socket(symbol=self._symbol, interval=Client.KLINE_INTERVAL_1MINUTE)

        # async manager to make sure ws is connected and opened
        async with kline_socket as stream:
            while True:
                try:
                    message = await stream.recv()
                    k = message['k']

                    candles_dict = {
                        "symbol": k['s'],
                        "interval": k['i'],
                        "open": float(k['o']),
                        "close": float(k['c']),
                        "high": float(k['h']),
                        "low": float(k['l']),
                        "volume": float(k['v']),
                        "is_closed": k['x'],
                        "start_time": k['t'],
                        "end_time": k['T'],
                        "source": "candlestick"
                    }
                    candlestick_channel = get_candlestick_channel(self._symbol)
                    self.publisher.publish(candlestick_channel, candles_dict)
                    kline_logger.info(f"{candles_dict['symbol']} | open: {float(k['o'])}, close: {float(k['c'])}, volume: {float(k['v'])}")

                    if self._kline_callbacks:
                        for _callback in self._kline_callbacks:
                            _callback(candles_dict)
                except Exception as e:
                    kline_logger.exception(f"Encountered issue in kline stream processing")
                
    """
    Place a limit order for SPOT trading
    """
    def place_limit_order(self, side: Side, price, quantity, tif='IOC') -> bool:
        try:
            if self._client is None:
                self._client = Client(self._api_key, self._api_secret)
                if self._testnet:
                    self._client.API_URL = "https://testnet.binance.vision/api"
            order_response = self._client.create_order(symbol=self._symbol,
                                              side=side.name,
                                              type='LIMIT',
                                              price=price,
                                              quantity=quantity,
                                              timeInForce=tif)
            polling_logger.info(f"Order submitted")
            return order_response['orderId']
        except Exception as e:
            polling_logger.info("Failed to place order: {}".format(e))
            return False

    """ 
    Register a depth callback function that takes one argument: (book: VenueOrderBook) 
    """
    def register_depth_callback(self, callback):
        self._depth_callbacks.append(callback)

    """ 
    Register an execution callback function that takes one argument, an order event: (event: OrderEvent) 
    """
    def register_polling_callback(self, callback):
        self._polling_callbacks.append(callback)

    def register_kline_callback(self, callback):
        self._kline_callbacks.append(callback)


# callback on order book update
def on_orderbook(order_book: VenueOrderBook):
    orderbook_logger.info("Receive order book: {}".format(order_book))

# callback on execution update
def on_polling(order_event: OrderEvent):
    polling_logger.info("Receive poll: {}".format(order_event))

def on_kline(order_event: OrderEvent):
    kline_logger.info("Receive kline: {}".format(order_event))


if __name__ == '__main__':
    # create a binance gateway object
    binance_gateway = BinanceGateway('BTCUSDT', redis_publisher=redis_publisher)

    # register callbacks
    binance_gateway.register_depth_callback(on_orderbook)
    binance_gateway.register_polling_callback(on_polling)
    binance_gateway.register_kline_callback(on_kline)

    # start connection
    binance_gateway.connection()

    send_order = True
    while True:
        time.sleep(2)

        if send_order:
            # place an order once
            ordered = binance_gateway.place_limit_order(Side.BUY, 25000, 0.1, 'GTC')
            if ordered:
                print(f"Order successfully placed")
            else:
                print(f"Failed to order")
            
            

