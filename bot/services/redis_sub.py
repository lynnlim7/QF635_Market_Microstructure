"""
Subscribe and listen to live market data
"""

import threading
from collections import defaultdict

import orjson
import redis

from bot.utils.config import settings
from bot.utils.logger import set_basic_logger

logger = set_basic_logger("redis_sub")

class RedisSubscriber:
    def __init__(self, channels: list[str]):
        self.redis_client = redis.Redis(
            host = settings.REDIS_HOST,
            port = settings.REDIS_PORT,
            db = settings.REDIS_DB,
            decode_responses=settings.REDIS_DECODE_RESPONSE
        )
        self.pubsub = self.redis_client.pubsub() 
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







