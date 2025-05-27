"""
Publish serialized market data from gateway to specified channel for other modules to subscribe
"""

import logging

import orjson
import redis

from bot.utils.config import settings


class RedisPublisher:
    def __init__(
            self,
            host = settings.REDIS_HOST,
            port = settings.REDIS_PORT,
            db = settings.REDIS_DB,
            decode_responses = settings.REDIS_DECODE_RESPONSE,
            prefix = settings.REDIS_PREFIX
            ):
        self.redis = redis.Redis(
            host=host,
            port=port,
            db=db, 
            decode_responses=decode_responses
        )
        self.prefix = prefix
        
    def create_channel(self, channel:str) -> str:
        return channel
    
    def publish(self, channel:str, data):
        try:
            redis_key = self.create_channel(channel)
            logging.info(f"Publishing to channel: {redis_key} with data: {data}")

            message = orjson.dumps(data)
            self.redis.set(redis_key,message)
            self.redis.publish(redis_key, message)

        except Exception as e:
            logging.error(f"Failed to publish: {e}")








        
        
        
