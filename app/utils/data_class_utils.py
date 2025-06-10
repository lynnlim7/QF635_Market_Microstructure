from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum


def to_clean_dict(obj):
    if not is_dataclass(obj):
        raise TypeError("Expected dataclass instance")

    def clean(val):
        if isinstance(val, Decimal):
            return float(val)
        if isinstance(val, Enum):
            return val.name
        return val

    return {k: clean(v) for k, v in asdict(obj).items()}
