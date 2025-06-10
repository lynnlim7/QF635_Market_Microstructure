import logging 
import time 
import redis 

from typing import Optional, Callable
from app.utils.config import settings 
from app.utils.logger import set_basic_logger

logger = set_basic_logger("circuit_breaker")

class RedisCircuitBreaker:
    def __init__(
            self,
            pool: redis.ConnectionPool,
            failure_threshold: int = 10, 
            success_threshold: int = 3,
            reset_timeout: int = 60,
        ):
        self.redis = redis.Redis.from_pool(pool)
        self.success_threshold = success_threshold
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout

        # redis keys 
        self.breaker_state = "circuit_breaker:state"
        self.failure_count = "circuit_breaker:failures"
        self.success_count = "circuit_breaker:success"
        self.failure_timestamp = "circuit_breaker:failure_time"
        self.trigger_breaker = "circuit_breaker:triggered"

        # initialize keys 
        if not self.redis.exists(self.breaker_state):
            self.redis.set(self.breaker_state, "closed")
            self.redis.set(self.failure_count, 0)
            self.redis.set(self.success_count, 0)
            self.redis.set(self.failure_timestamp, 0)
            self.redis.set(self.trigger_breaker, 0)
            logger.info("Circuit breaker initialized in closed state.")

    def get_state(self) -> str:
        state = self.redis.get(self.breaker_state)
        if state is None:
            return "closed"
        if isinstance(state, bytes):
            return state.decode('utf-8')
        return state

    def allow_request(self) -> bool:
        current_timestamp = int(time.time())
        latest_failure = int(self.redis.get(self.failure_timestamp) or 0)

        if self.get_state() == "closed":
            return True 
        
        if self.get_state() == "open":
            if (current_timestamp - latest_failure) >= self.reset_timeout:
                self.redis.set(self.breaker_state, "closed")
                self.redis.set(self.failure_count, 0)
                self.redis.set(self.success_count, 0)
                logger.info("Circuit breaker reset after timeout period")
                return True
            return False
        return True

    def record_success(self):
        if self.get_state() == "open":
            return 
        
        success_count = self.redis.incr(self.success_count)
        logger.info(f"Attempt success after timeout. Current success count {success_count}.")

        if success_count >= self.success_threshold:
            self.redis.set(self.breaker_state, "closed")
            self.redis.set(self.failure_count, 0)
            self.redis.set(self.success_count, 0)
            logger.info(f"Circuit breaker closed after {success_count} successful attempts.")

    def record_failure(self):
        failure_count = self.redis.incr(self.failure_count)
        self.redis.set(self.failure_timestamp, int(time.time()))
        logger.info(f"Attempt failed. Current failure count {failure_count}.")

        if failure_count >= self.failure_threshold:
            self.redis.set(self.breaker_state, "open")
            self.redis.set(self.trigger_breaker, 1)
            logger.warning(f"Circuit breaker opened after {failure_count} failures.")

    def force_open(self, reason: str = None):
        if self.get_state() == "closed":
            self.redis.set(self.breaker_state, "open")
            self.redis.set(self.trigger_breaker, 1)
            logger.warning(f"Circuit breaker forced open. Reason: {reason}")


   




        
    

    
    



