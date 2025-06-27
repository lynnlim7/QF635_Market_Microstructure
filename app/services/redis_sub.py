"""
Subscribe and listen to live market data
"""

import threading
from collections import defaultdict

import orjson
import redis
import redis.asyncio as aredis

from app.utils.config import settings
from app.utils.logger import set_basic_logger
from app.services.circuit_breaker import RedisCircuitBreaker
from typing import List, AsyncGenerator
import asyncio
import msgspec
from app.common.interface_message import RedisMessage
from queue import Queue


logger = set_basic_logger("redis_sub")

__all__ = [
    "RedisSubscriber",
    "RedisAsyncSubscriber"
]

class RedisSubscriber:
    def __init__(
            self, 
            pool: redis.ConnectionPool,
            channels: list[str],
            circuit_breaker = RedisCircuitBreaker,
        ):
        self.redis = redis.Redis.from_pool(pool)
        self.pubsub = self.redis.pubsub() 
        self.circuit_breaker = circuit_breaker
        self.pubsub.subscribe(*channels) # subscribe to multiple redis channels
        self.redis_handlers = defaultdict(list) # initialize dict to map to list of callback funcs 
    
    # route to multiple modules
    def register_handler(self, channel: str, callback: callable):
        self.redis_handlers[channel].append(callback)

    def start_subscribing(self):
        def _listen():
            for message in self.pubsub.listen():
                # check for message pub/sub component
                if message['type'] != "message":
                    continue
                channel = message['channel']
                try:
                    data = orjson.loads(message["data"])
                    handlers = self.redis_handlers.get(channel, [])
                    for handler in handlers:
                        handler(data)
                except Exception as e:
                    logger.error(f"Error in handling message:{e}")
        threading.Thread(target=_listen, daemon=True).start()

    @classmethod
    def from_pool(cls, pool, channels) : 
        return cls(pool, channels)

    
class RedisAsyncSubscriber : 
    def __init__(
            self,
            pool : aredis.ConnectionPool,
            event_loop : asyncio.AbstractEventLoop,
            channels : List[str], 
            q : Queue,
            circuit_breaker = RedisCircuitBreaker,
    ) : 
        self._loop = event_loop
        self.redis = aredis.Redis.from_pool(pool)
        self.pubsub = self.redis.pubsub()
        self.channels = channels
        self.q = q

        self.decoder = msgspec.msgpack.Decoder(RedisMessage)

    async def recv(self) :
        await self.start()
        decoder = self.decoder
        q = self.q
        while True : 
            msg = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            if msg :
                try :
                    decoded = decoder.decode(msg["data"])
                    self._loop.run_in_executor(None, q.put, decoded)
                except Exception as e : 
                    print(f'Unable to process {msg["data"]}')

    async def start(self) : 
        print("subscribing ... ")
        await self.pubsub.subscribe(*self.channels)
        print(f"subscribed to {self.channels}")


    @classmethod
    def from_pool(cls, pool, channels, event_loop, q) :
        return cls(
            pool=pool,
            event_loop=event_loop,
            channels=channels,
            q=q
        )

    def start_subscribing(self) :
        asyncio.run_coroutine_threadsafe(self.recv(), loop=self._loop)



