from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
import os

from decimal import getcontext, ROUND_HALF_UP

getcontext().prec = 38  # total digits of precision (like SQL Decimal(38,18))
getcontext().rounding = ROUND_HALF_UP

class Settings(BaseSettings):
    BINANCE_TEST_API_KEY: str = os.getenv("BINANCE_TESTNET_API_KEY", "")
    BINANCE_TEST_API_SECRET: str = os.getenv("BINANCE_TESTNET_SECRET_KEY", "")

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_ignore_empty=True,
        env_file_encoding='utf-8',
        extra="ignore"
    )

    # Symbol
    SYMBOL: str = "BTCUSDT"

    # Redis config
    # if running whole application in docker, use "redis"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PW: str | None = None
    REDIS_SSL: bool = False
    REDIS_MAX_CONNECTIONS: int = 10
    REDIS_SOCKET_TIMEOUT: float = 5.0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 5.0
    REDIS_RETRY_ON_TIMEOUT: float = 5.0
    REDIS_HEALTH_CHECK_INTERVAL: int = 30
    REDIS_DECODE_RESPONSE: bool = True 
    REDIS_PREFIX: str = "market_data"

    # Risk management 
    MAX_RISK_PER_TRADE_PCT: float = 0.01 # 1% risk per trade
    MAX_ABSOLUTE_DRAWDOWN: float = 0.10 # 10% equity
    MAX_RELATIVE_DRAWDOWN: float = 0.05 # 5% daily
    MAX_SPREAD_PCT: float = 0.003

    # Scoring Parameters
    SIGNAL_SCORE_BUY: float = 1.0
    SIGNAL_SCORE_SELL: float = -1.0
    SIGNAL_SCORE_HOLD: float  = 0

    #PG config
    APP_PG_HOST: str = os.getenv("APP_PG_HOST", "")
    APP_PG_USER: str = os.getenv("APP_PG_USER", "")
    APP_PG_PASSWORD: str = os.getenv("APP_PG_PASSWORD", "")
    APP_PG_PORT: str = os.getenv("APP_PG_PORT", "5432")
    APP_PG_DB:str = os.getenv("APP_PG_DB", "postgres")



settings = Settings()

