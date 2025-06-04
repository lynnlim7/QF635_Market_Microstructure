from app.utils.config import settings

def get_candlestick_channel(symbol:str) -> str:
    return f"{settings.REDIS_PREFIX}:candlestick:{symbol.lower()}"

def get_orderbook_channel(symbol: str) -> str:
    return f"{settings.REDIS_PREFIX}:orderbook:{symbol.lower()}"

def get_execution_channel(symbol: str) -> str:
    return f"{settings.REDIS_PREFIX}:execution:{symbol.lower()}"