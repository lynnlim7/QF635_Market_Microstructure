"""
Publish serialized market data from gateway to specified channel for other modules to subscribe
"""

import logging

import orjson
import redis
import redis.asyncio as aredis
from app.services.circuit_breaker import RedisCircuitBreaker

from app.utils.config import settings

import msgspec
import uuid
import asyncio
from app.common.interface_message import RedisMessage



__all__ = [
    "RedisPublisher",
    "RedisAsyncPublisher"
]

class RedisPublisher:
    def __init__(
            self,
            pool : redis.ConnectionPool,
            circuit_breaker: RedisCircuitBreaker,
            prefix = settings.REDIS_PREFIX,
            ):
        self.redis = redis.Redis.from_pool(pool)
        self.prefix = prefix
        self.circuit_breaker = circuit_breaker
        
    def create_channel(self, channel:str) -> str:
        return channel
    
    def publish(self, channel:str, data):
        try:
            if not self.circuit_breaker.allow_request():
                logging.warning(f"Circuit breaker is open - stop publishing to {channel}")
                return

            redis_key = self.create_channel(channel)
            logging.info(f"Publishing to channel: {redis_key} with data: {data}")

            message = orjson.dumps(data)
            self.redis.set(redis_key,message)
            self.redis.publish(redis_key, message)

        except Exception as e:
            logging.error(f"Failed to publish: {e}")

    def _close(self) : 
        self.redis.close()

    def __enter__(self) :
        return self
    
    def __exit__(self) : 
        self._close()

    @classmethod
    def from_pool(cls, pool, circuit_breaker) :
        return cls(pool, circuit_breaker)


class RedisAsyncPublisher :
    def __init__(
            self,
            pool : aredis.ConnectionPool,
            event_loop : asyncio.AbstractEventLoop, 
            prefix = settings.REDIS_PREFIX,
            default_expiry = 180,
        ):
        self._loop = event_loop
        asyncio.set_event_loop(self._loop)
        self.redis = aredis.Redis.from_pool(pool)
        self.prefix = prefix
        self.encoder = msgspec.msgpack.Encoder()
        self.default_expiry = default_expiry

    async def __aenter__(self) : 
        return self
    
    async def __aexit__(self, exc_type, exc_value, exc_tb):
        await self._close()

    async def _close(self) : 
        await self.redis.close()

    def shutdown(self):
        fut = asyncio.run_coroutine_threadsafe(self._close(), self._loop)
        fut.result()
        
    async def publish(self, channel:str, data:msgspec.Struct, topic:str, set_key:bool =False, correlation_id:str = ""):
        envelope = RedisMessage(
            value=data,
            topic=topic, 
            correlation_id=correlation_id
        )
        msg = self.encoder.encode(envelope)
        try:
            redis_key = channel
            logging.debug(f"Publishing to channel: {redis_key} with data: {msg}")
            tasks = []
            if set_key : 
                tasks.append(self.redis.set(redis_key, msg, ex=self.default_expiry))
            tasks.append(self.redis.publish(redis_key, msg))
            await asyncio.gather(*tasks)
        except Exception as e:
            logging.error(f"Failed to publish: {e}")


    def publish_sync(self, channel : str, data: msgspec.Struct, topic:str, set_key=True, correlation_id=""):
        try : 
            fut = asyncio.run_coroutine_threadsafe(
                self.publish(channel, data, topic, set_key, correlation_id), self._loop
            )
            return fut.result()
        except Exception as e :
            logging.error(f"Publish sync failed : {e}")
            
    @classmethod
    def from_pool(cls, pool : aredis.ConnectionPool, event_loop : asyncio.AbstractEventLoop) :
        return cls(
            pool=pool, 
            event_loop=event_loop
        )







        
        
        
