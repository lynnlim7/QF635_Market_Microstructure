import redis
import redis.asyncio as aredis

from app.utils.config import settings
from app.services.redis_pub import RedisPublisher, RedisAsyncPublisher
from app.services.redis_sub import RedisSubscriber, RedisAsyncSubscriber
from app.services.circuit_breaker import RedisCircuitBreaker
from typing import Union
import asyncio
import threading
from queue import Queue

__all__ = [
    "RedisPool"
]

class RedisPool : 
    def __init__(
            self,
            host = settings.REDIS_HOST,
            port = settings.REDIS_PORT,
            db = settings.REDIS_DB,
            decode_responses = settings.REDIS_DECODE_RESPONSE,
            async_pool=False,
    ):
        self.async_pool = async_pool

        if async_pool : 
            self.pool = aredis.ConnectionPool(
                host=host,
                port=port,
                db=db,
                decode_responses=decode_responses
            )

        else :
            self.pool = redis.ConnectionPool(
                host=host,
                port=port,
                db=db,
                decode_responses=decode_responses
            )
        self._circuit_breaker = None

    def create_circuit_breaker(self) -> RedisCircuitBreaker:
        if self._circuit_breaker is None:
            redis_client = redis.Redis.from_pool(self.pool)
            self._circuit_breaker = RedisCircuitBreaker(redis_client.connection_pool)
        return self._circuit_breaker
    

    def start(self) : 
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        return self._thread

    def create_publisher(self, prefix : str ="") -> Union[RedisPublisher, RedisAsyncPublisher] :
        if self.async_pool :
            return RedisAsyncPublisher.from_pool(self.pool, event_loop=self._loop)
        else :
            return RedisPublisher.from_pool(self.pool, self._circuit_breaker)
        
    def create_subscriber(self, channels, q : Queue = None) -> Union[RedisSubscriber, RedisAsyncSubscriber]:
        if self.async_pool :
            return RedisAsyncSubscriber.from_pool(self.pool, channels=channels, event_loop=self._loop, q=q)
        else :
            return RedisSubscriber.from_pool(self.pool, channels)

    @property
    def circuit_breaker(self):
        return self._circuit_breaker
