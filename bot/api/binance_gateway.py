## Binance Gateway Implementation 
# WebSocket API to get live data

import websocket 
import asyncio
import logging
import orjson # exploratory: faster JSON
from interfaces.logger import setup_logger
import threading


