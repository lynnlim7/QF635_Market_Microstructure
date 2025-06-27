import msgspec
from enum import Enum
from app.utils.config import settings

class StrategySignal(Enum) : 
    BUY : float = settings.SIGNAL_SCORE_BUY
    HOLD : float = settings.SIGNAL_SCORE_HOLD
    SELL : float = settings.SIGNAL_SCORE_SELL

class RiskManagerSignal(msgspec.Struct, gc=False, array_like=True) : 
    signal : StrategySignal
    symbol : str

