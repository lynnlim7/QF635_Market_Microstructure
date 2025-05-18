import msgspec

__all__ = ["RawMultistreamMsg"]

class RawMultistreamMsg(msgspec.Struct, gc=False, omit_defaults=True) : 
    stream : str
    data : msgspec.Raw