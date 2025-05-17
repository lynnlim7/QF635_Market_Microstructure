## Binance Gateway Implementation
# WebSocket to fetch live data

# TODO: refer to binance gateway template and store data in redis + try to fetch the data for all other modules 

import asyncio
from binance.depthcache import FuturesDepthCacheManager
from binance import AsyncClient, BinanceSocketManager, Client
from dotenv import load_dotenv
from bot.utils.logger import setup_logger
from bot.utils.config import settings
import orjson
from loguru import logger
import os
import redis
from bot.services.redis_service import RedisPublisher
from bot.common.interface_book import VenueOrderBook, PriceLevel, OrderBook
from bot.common.interface_order import OrderEvent, OrderStatus, ExecutionType, Side
from bot.config.settings import BINANCE_API_KEY, BINANCE_API_SECRET
import time
from threading import Thread
import websockets

# from db.database_insert import create_table
# from base_sql import Session

logger = setup_logger("Gateway", logger_path="./logs")
logger.info("Console logging")

# initialize redis pub
redis_publisher = RedisPublisher(prefix="market_data")

load_dotenv()

class BinanceGateway:
    def __init__(self, symbol:str, api_key=None, api_secret=None, name="", testnet=True, publisher: RedisPublisher=None):
        self._api_key = api_key
        self._api_secret = api_secret
        self._exchange_name = name 
        self._symbol = symbol
        self._testnet = testnet
        self.publisher = publisher

        # binance async client
        self._client = None
        self._async_client = None
        self._dcm = None  # depth cache, which implements the logic to manage a local order book
        self._dws = None  # depth async WebSocket session

        # depth cache
        self._depth_cache = None

        # loop and dedicated thread to run all async concurrent tasks
        self._loop = asyncio.new_event_loop()
        self._loop_thread = Thread(target=self._run_async_tasks, daemon=True, name=name)

        # callbacks
        self._depth_callbacks = []
        self._execution_callbacks = []

        # initialize client 
        self.client = Client(
                api_key=settings.BINANCE_API_KEY,
                api_secret=settings.BINANCE_API_SECRET
        )

    def connection(self):
        logger.info("Initializing connection...")
        self._loop.run_until_complete(self._reconnect_ws())
        logger.info("Starting event loop thread...")
        self._loop_thread.start()

    # an internal method to reconnect websocket
    async def _reconnect_ws(self):
        logger.info("reconnecting websocket")
        self._async_client = await AsyncClient.create(self._api_key, self._api_secret, testnet=self.testnet)

    # an internal method to runs tasks in parallel
    def _run_async_tasks(self):
        """ Run the following tasks concurrently in the current thread """
        self._loop.create_task(self._listen_depth_forever())
        self._loop.create_task(self._listen_execution_forever())
        self._loop.run_forever()

    # an internal async method to listen to depth stream
    async def _listen_depth_forever(self):
        logger.info("Subscribing to depth events")
        while True:
            if not self._dws:
                logger.info("Depth socket not connected, reconnecting...")
                self._dcm = FuturesDepthCacheManager(self._async_client, symbol=self._symbol)
                self._dws = await self._dcm.__aenter__()

            # wait for depth update
            try:
                self._depth_cache = await self._dws.recv()

                if self._depth_callbacks:
                    # notify callbacks
                    for _callback in self._depth_callbacks:
                        _callback(VenueOrderBook(self._exchange_name, self.get_order_book()))
            except Exception as e:
                logger.exception('Encountered issue in depth processing')
                # reset socket and reconnect
                self._dws = None
                await self._reconnect_ws()

    # an internal async method to listen to user data stream
    async def _listen_execution_forever(self):
        logger.info("Subscribing to user data events")
        _listen_key = await self._async_client.futures_stream_get_listen_key()
        if self.testnet:
            url = 'wss://stream.binancefuture.com/ws/' + _listen_key
        else:
            url = 'wss://fstream.binance.com/ws/' + _listen_key

        conn = websockets.connect(url)
        ws = await conn.__aenter__()
        while ws.open:
            _message = await ws.recv()
            # logging.info(_message)

            # convert to json
            _data = json.loads(_message)
            update_type = _data.get('e')

            if update_type == 'ORDER_TRADE_UPDATE':
                _trade_data = _data.get('o')
                _order_id = _trade_data.get('c')
                _symbol = _trade_data.get('s')
                _execution_type = _trade_data.get('x')
                _order_status = _trade_data.get('X')
                _side = _trade_data.get('S')
                _last_filled_price = float(_trade_data.get('L'))
                _last_filled_qty = float(_trade_data.get('l'))

                # create an order event
                _order_event = OrderEvent(_symbol, _order_id, ExecutionType[_execution_type], OrderStatus[_order_status])
                _order_event.side = Side[_side]
                if _execution_type == 'TRADE':
                    _order_event.last_filled_price = _last_filled_price
                    _order_event.last_filled_quantity = _last_filled_qty

                # notify callbacks
                if self._execution_callbacks:
                    # notify callbacks
                    for _callback in self._execution_callbacks:
                        _callback(_order_event)

    """ 
    Get order book 
    """
    def get_order_book(self) -> VenueOrderBook:
        bids = [PriceLevel(price=p, size=s) for (p, s) in self._depth_cache.get_bids()[:5]]
        asks = [PriceLevel(price=p, size=s) for (p, s) in self._depth_cache.get_asks()[:5]]
        return OrderBook(timestamp=self._depth_cache.update_time, contract_name=self._symbol, bids=bids, asks=asks)

    """
    Place a limit order
    """
    def place_limit_order(self, side: Side, price, quantity, tif='IOC') -> bool:
        try:
            self._client.futures_create_order(symbol=self._symbol,
                                              side=side.name,
                                              type='LIMIT',
                                              price=price,
                                              quantity=quantity,
                                              timeInForce=tif)
            return True
        except Exception as e:
            logger.info("Failed to place order: {}".format(e))
            return False

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


# callback on order book update
def on_orderbook(order_book: VenueOrderBook):
    logger.info("Receive order book: {}".format(order_book))


# callback on execution update
def on_execution(order_event: OrderEvent):
    logger.info("Receive execution: {}".format(order_event))


if __name__ == '__main__':
    # get api key and secret
    dotenv_path = '/vault/binance_keys'
    load_dotenv(dotenv_path=dotenv_path)
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')

    # create a binance gateway object
    binance_gateway = BinanceGateway('BTCUSDT', api_key, api_secret)

    # register callbacks
    binance_gateway.register_depth_callback(on_orderbook)
    binance_gateway.register_execution_callback(on_execution)

    # start connection
    binance_gateway.connect()

    send_order = True
    while True:
        time.sleep(2)

        if send_order:
            # place an order once
            binance_gateway.place_limit_order(Side.BUY, 25000, 0.1, 'GTX')
            send_order = False












# client = Client(
#             os.getenv('BINANCE_API_KEY'),
#             os.getenv('BINANCE_API_SECRET')
# )

# initialize connection to redis
r = redis.Redis(host="localhost", port=6379, decode_response=False)

# # create table 
# create_table()

# # create session
# session = Session()

BINANCE_SOCKET = settings.BINANCE_WS_URL
# relative strength index (rsi) momentum indicator
RSI_PERIOD = 14 # calc over 14 candles (3m each)
RSI_OVERBOUGHT = 70 # trigger sell signal
RSI_OVERSOLD = 30 # trigger buy signal
TRADE_SYMBOL = "BTCUSDT"
TRADE_SIZE = 0.05
closed_prices = [] # store closing price of candles to calc rsi
in_position = False

def order(side, size, order_type=Client.ORDER_TYPE_MARKET, symbol=TRADE_SYMBOL):
    try: 
        order = client.create_order(
            symbol=symbol,
            side=side,
            type=order_type,
            quantity=size
        )
        logging.info(f"Order was successful: {order}")
        return order
    except Exception as e:
        logging.error(f"Order failed: {e}")
        return None
    
# establish websocket connection
def on_open(ws):
    print("Connection opened")

def on_close(ws):
    print("Connection closed")

def on_error(ws, error):
    print(f"Error:{error}")

def on_message(ws, message):
    global closed_prices, in_position
    message = orjson.loads(message)
    # session = Session()
    candle = message['data']['k']
    trade_symbol = candle['s']
    is_candle_closed = candle['x'] # bool|true/false
    open = candle['o']
    closed = candle['c']
    high = candle["h"]
    low = candle["l"]
    volume = candle["v"]
    interval = candle['i']
    closed_prices.append(float(closed))

    # k,v pair to add to Redis queue
    message_dict = {
        "symbol" : trade_symbol,
        "open_price" : open,
        "close_price" : closed,
        "high_price" : high,
        "low_price" : low,
        "volume" : volume,
    }

    # store multiple keys per symbol
    redis_key = f"crypto:{trade_symbol}"
    r.hset(redis_key, mapping=message_dict)

    print(f"Stored {redis_key} in Redis")




















