from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
import os

# ENV_PATH = Path("/Users/Lynn/Documents/coding_workspace/qf635_market_microstructure_algo_trading/.env")
class Settings(BaseSettings):
    REDIS_URL: str
    DB_URL: str
    BINANCE_WS_URL: str

    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_ignore_empty=True,
        extra="ignore"
    )
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PW: str | None = None
    REDIS_SSL: bool = True
    REDIS_MAX_CONNECTIONS: int = 10
    REDIS_SOCKET_TIMEOUT: float = 5.0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 5.0
    REDIS_RETRY_ON_TIMEOUT: float = 5.0
    REDIS_HEALTH_CHECK_INTERVAL: int = 30
    REDIS_DECODE_RESPONSE: bool = False 
    REDIS_PREFIX: str = "market_data"

settings = Settings()

