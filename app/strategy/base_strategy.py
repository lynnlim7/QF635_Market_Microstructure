
from abc import ABC, abstractmethod

from app.api.binance_gateway import BinanceGateway
from app.common.interface_message import RedisMessage

import threading
import msgspec
import asyncio
from queue import Queue
from collections import defaultdict
from app.common.interface_api import FuturesClosingPricesRequest, FuturesKlineBulk
from app.common.interface_risk import RiskManagerSignal
from app.common.interface_book import KlineEvent
from app.services import RedisPool
import uuid
from typing import Union
from app.utils.config import settings 

class StrategyABC(ABC):
    @abstractmethod
    def __init__(self, symbol: str,api: BinanceGateway, config: dict = None):
        """Initialize the strategy with symbol and config."""
        pass

    @abstractmethod
    def update_data(self, data):
        """Feed new live or simulated data into the strategy."""
        pass

    @abstractmethod
    def generate_signal(self) -> int:
        """Generate trading signal: 1=Buy, -1=Sell, 0=Hold."""
        pass

    @abstractmethod
    def get_state(self) -> dict:
        """Return current strategy state (for logs or dashboard)."""
        pass


class BaseStrategy(StrategyABC) :
    def __init__(self, redis_pool : RedisPool) : 
        self._Channels = [
            'market_data:candlestick:*',
            'market_data:orderbook:*'
        ]
        self._initialize_data = True
        self.response_promise = defaultdict(lambda : asyncio.Queue(1))
        self.redis_pool= redis_pool

    async def get_from_queue(self, q: Queue) -> RedisMessage :
        loop = self._loop
        return await loop.run_in_executor(None, q.get)

    def _create_promise(self) -> str : 
        correlation_id = str(uuid.uuid4())
        self.response_promise[correlation_id] = asyncio.Queue(1)
        return correlation_id
    
    def _wait_response(self, correlation_id) :
        response_fut = asyncio.run_coroutine_threadsafe(self._wait_promise(correlation_id), loop=self._loop)
        response = response_fut.result()
        return response
    
    def _request_and_wait(self, topic, channel, payload) : 
        correlation_id = self._create_promise()
        self._publisher.publish_sync(channel, payload, topic, set_key=False, correlation_id=correlation_id)
        response = self._wait_response(correlation_id)
        return response    


    
    def initialize_data(self) : 
        if self._initialize_data : 
            self.data = self.request_api("close")

    def request_api(self, topic: str, params: dict = {}) :
        if topic == "close" : 
            publish_channel = "API@close"
            payload = FuturesClosingPricesRequest.from_dict(params)
            response = self._request_and_wait(topic, publish_channel, payload=payload)
            decoder = msgspec.msgpack.Decoder(type=FuturesKlineBulk) 
            if response : 
                df = decoder.decode(response).to_df()
                return df
            
            
    async def accept_message(self) :
        candlestick_decoder = msgspec.msgpack.Decoder(KlineEvent)

        while True : 
            msg = await self.get_from_queue(self._subscriber_queue)
            if msg.topic == "response" :
                if msg.correlation_id in self.response_promise : 
                    await self.response_promise[msg.correlation_id].put(msg.value)
            elif msg.topic == "candlestick" : 
                candlestick_decoded = candlestick_decoder.decode(msg.value)
                self.update_data(candlestick_decoded)

    def publish_signal(self, symbol, signal : float) :
        signal_channel = "Signal"
        data = RiskManagerSignal(signal=signal, symbol=symbol)
        self._publisher.publish_sync(signal_channel, data=data, topic="signal")

    async def get_from_queue(self, q : Queue) -> RedisMessage :
        loop = self._loop
        return await loop.run_in_executor(None, q.get)

    async def _wait_promise(self, correlation_id) : 
        q = self.response_promise[correlation_id]
        out = await q.get()
        del self.response_promise[correlation_id]
        return out

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
