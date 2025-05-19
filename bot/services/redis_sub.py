"""
Subscribe and listen to live market data
"""

from typing import Any
import logging
import redis 
import orjson
from bot.utils.logger import setup_logger
from bot.utils.config import settings
import threading
import time

def handle_candle(data):
        print(f"🛠️ Received candlestick: {data}")  

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
        self.redis_handlers = {} # initialize dict to map to callback funcs 
    
    # route to other modules
    def register_handler(self, channel: str, callback: callable):
        self.redis_handlers[channel] = callback

    def start_subscribing(self):
        def _listen():
            for message in self.pubsub.listen():
                # check for message pub/sub component
                if message['type'] != "message":
                    continue
                channel = message['channel']
                try:
                    data = orjson.loads(message["data"])
                    if handler := self.redis_handlers.get(channel):
                        handler(data)
                except Exception as e:
                    print(f"Error in handling message:{e}")
        threading.Thread(target=_listen, daemon=True).start()







