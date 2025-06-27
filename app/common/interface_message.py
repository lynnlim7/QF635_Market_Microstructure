import msgspec
from typing import Optional

class RedisMessage(msgspec.Struct, gc=False, array_like=True) : 
    topic : str
    value : msgspec.Raw
    correlation_id : Optional[str] = None

class DummyMessage(msgspec.Struct, array_like=True, gc=False):
    p: bool

class RequestNotification(DummyMessage):

    @classmethod
    def create(cls) : 
        return cls(True)