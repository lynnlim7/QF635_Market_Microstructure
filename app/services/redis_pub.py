"""
Publish serialized market data from gateway to specified channel for other modules to subscribe
"""

import logging

import orjson
import redis
import redis.asyncio as aredis
from app.services.circuit_breaker import RedisCircuitBreaker

from app.utils.config import settings

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
    def from_pool(cls, pool) : 
        return cls(pool)


class RedisAsyncPublisher :
    def __init__(
            self,
            pool : aredis.ConnectionPool,
            prefix = settings.REDIS_PREFIX
        ):
        self.redis = aredis.Redis.from_pool(pool)
        self.prefix = prefix

    def _close(self) : 
        self.redis.close()

    def __aenter__(self) : 
        return self
    
    def __aexit__(self) : 
        return self.close()
    
    async def publish(self, channel:str, data):
        try:
            redis_key = self.create_channel(channel)
            logging.info(f"Publishing to channel: {redis_key} with data: {data}")

            message = orjson.dumps(data)
            await self.redis.set(redis_key,message)
            await self.redis.publish(redis_key, message)
        except Exception as e:
            logging.error(f"Failed to publish: {e}")

    @classmethod
    def from_pool(cls, pool) : 
        return cls(pool)







        
        
        
