from app.utils.logger import setup_logger
from app.utils.config import settings
from typing import Optional, Dict, Any
import time

circuit_breaker_logger = setup_logger(
    logger_name="circuit_breaker",
    logger_path="./logs/circuit_breaker",
    log_type="circuit_breaker",
    enable_console=True
)

class CircuitBreaker:
    def __init__(self,
                 active_kill_switch:False,
                 kill_switch_reason
                 ):
    def trigger_kill_switch(self, reason:str) -> bool:
        

    

    