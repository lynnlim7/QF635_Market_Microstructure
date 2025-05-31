from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import MetaData
import os


DEFAULT_SCHEMA = "trading_app"

metadata = MetaData(schema=os.environ.get("APP_SCHEMA", DEFAULT_SCHEMA))
Base = declarative_base(metadata=metadata)

from bot.models.assets import *
from bot.models.portfolio import * 
from bot.models.trades import *
