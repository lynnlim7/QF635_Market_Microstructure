"""
Publish serialized market data from gateway to specified channel for other modules to subscribe
"""

from typing import any
from loguru import logger
import threading
import redis 
import orjson
from bot.utils.logger import setup_logger
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
        return f"{self.prefix}: {channel}" if self.prefix else channel
    
    def publish(self, channel:str, data):
        try:
            created_channel = self.create_channel(channel)
            message = orjson.dumps(data) # serialize data
            self.redis.publish(created_channel, data)
        except Exception as e:
            logger.error(f"Failed to publish data: {e}")





        
        
        
