from enum import Enum

class REDIS_DB_NUM(Enum) :
    SPOT = 0
    FUTURES = 1

class TimeInterval(Enum):
    S1 = "1s"

    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"

    H1 = "1h"
    H2 = "2h"
    H4 = "4h"
    H6 = "6h"
    H8 = "8h"
    H12 = "12h"

    D1 = "1d"
    D3 = "3d"

    W1 = "1w"

    def __str__(self):
        return self.value