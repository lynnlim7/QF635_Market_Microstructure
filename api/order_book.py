import logging 
import logging
import os
import time
from dotenv import load_dotenv
from interfaces.logger import setup_logger
from api.binance_gateway import BinanceGateway, ProductType

