import msgspec

__all__ = ["RawMultistreamMsg"]

class RawMultistreamMsg(msgspec.Struct) : 
    stream : str
    data : msgspec.Raw