import msgspec
from decimal import Decimal
from typing import List, Union
from enum import Enum
from app.common.interface_order import OrderType, Side
import pandas as pd

class KlineIntervals(Enum) :
    KLINE_INTERVAL_1SECOND = "1s"
    KLINE_INTERVAL_1MINUTE = "1m"
    KLINE_INTERVAL_3MINUTE = "3m"
    KLINE_INTERVAL_5MINUTE = "5m"
    KLINE_INTERVAL_15MINUTE = "15m"
    KLINE_INTERVAL_30MINUTE = "30m"
    KLINE_INTERVAL_1HOUR = "1h"
    KLINE_INTERVAL_2HOUR = "2h"
    KLINE_INTERVAL_4HOUR = "4h"
    KLINE_INTERVAL_6HOUR = "6h"
    KLINE_INTERVAL_8HOUR = "8h"
    KLINE_INTERVAL_12HOUR = "12h"
    KLINE_INTERVAL_1DAY = "1d"
    KLINE_INTERVAL_3DAY = "3d"
    KLINE_INTERVAL_1WEEK = "1w"
    KLINE_INTERVAL_1MONTH = "1M"



class _FuturesAccountBalance(msgspec.Struct, array_like=True, frozen=True) : 
    accountAlias : str
    asset : str
    balance :  Decimal
    crossWalletBalance:  Decimal 
    crossUnPnl:  Decimal
    availableBalance:  Decimal
    maxWithdrawAmount:  Decimal
    marginAvailable: bool
    updateTime: int

class FuturesAccountBalance(msgspec.Struct, array_like=True, frozen=True) : 
    errMsg : str = ""
    acc : List[_FuturesAccountBalance] = []

class FuturesAPIOrder(msgspec.Struct, array_like=True, frozen=True) : 
    order_type : OrderType
    side : Side
    price : float
    qty : float
    symbol : str = ""

    @classmethod
    def create_order(
        cls,
        order_type : Union[str, OrderType],
        side : Union[str, Side],
        price : float,
        qty : float,
        symbol : str = ""
    ) : 
        if not isinstance(order_type, str, OrderType) : 
            raise TypeError(f'Invalid Type for order_type received \"{type(order_type)}\"')
        

        if not isinstance(side, str, Side) : 
            raise TypeError(f'Invalid Type for side received \"{type(side)}\"')
        
        if not side.lower() in {'buy', 'sell'} : 
            raise ValueError(f'Unknown value for side received \"{side}\"')
        
        order_type_mapping = {
            'market' : OrderType.Market,
            'limit' : OrderType.Limit,
            'take_profit' : OrderType.TakeProfit,
            'stop_loss' : OrderType.StopMarket,
        }

        if isinstance(order_type, str) : 
            order_type = order_type_mapping[order_type.lower()]

        return cls(
            order_type=order_type, 
            side=side,
            price=price,
            qty=qty,
            symbol=symbol,
        )
    
class _FuturesPosition(msgspec.Struct, array_like=True, frozen=True):
    symbol: str
    positionSide: str
    positionAmt: Decimal
    entryPrice: Decimal
    breakEvenPrice: Decimal
    markPrice: Decimal
    unRealizedProfit: Decimal
    liquidationPrice: Decimal
    isolatedMargin: Decimal
    notional: Decimal
    marginAsset: str
    isolatedWallet: Decimal
    initialMargin: Decimal
    maintMargin: Decimal
    positionInitialMargin: Decimal
    openOrderInitialMargin: Decimal
    adl: int
    bidNotional: Decimal
    askNotional: Decimal
    updateTime: int

class FuturesPositionResponse(msgspec.Struct, array_like=True, frozen=True):
    errMsg: str = ""
    acc: List[_FuturesPosition] = []

    @classmethod
    def from_list(cls, data) : 
        typed_data = msgspec.convert(data, list[_FuturesPosition])
        return cls(acc=typed_data)

class _FuturesKlineRecord(msgspec.Struct, array_like=True, frozen=True, gc=False) : 
    timestamp: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time: int
    quote_asset_volume: Decimal
    number_of_trades: int
    taker_buy_base_asset_volume: Decimal
    taker_buy_quote_asset_volume: Decimal
    ignore: int

class FuturesKlineBulk(msgspec.Struct, array_like=True, frozen=True) :
    records : List[_FuturesKlineRecord] = []

    @classmethod
    def from_list(cls, data) : 
        typed_data = msgspec.convert(data, list[_FuturesKlineRecord])
        return cls(records=typed_data)
    
    def to_df(self) -> pd.DataFrame :
        df = pd.DataFrame(
            [msgspec.to_builtins(r) for r in self.records]
        )
        numeric_columns = ["open", "high", "low", "close", "volume",
                            "quote_asset_volume", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume"]
        df[numeric_columns] = df[numeric_columns].astype(float)
        df = df.drop(columns=['ignore'])
        return df
    
class _FuturesClosingPrice(msgspec.Struct, array_like=True, frozen=True) :
    timestamp : int
    close : Decimal

class FuturesClosingPrices(msgspec.Struct, array_like=True, frozen=True) :
    records : List[_FuturesClosingPrice] = []

    @classmethod
    def from_bulk(cls, data : FuturesKlineBulk) : 
        records = [_FuturesClosingPrice(timestamp=r.timestamp, close=r.close) for r in data.records]
        return cls(records=records)
    
class FuturesClosingPricesRequest(msgspec.Struct, array_like=True, frozen=True) :
    symbol : str = "BTCUSDT"
    interval : KlineIntervals = KlineIntervals.KLINE_INTERVAL_1MINUTE
    limit : int = 200

    @classmethod
    def from_dict(cls, data) : 
        return cls(
            symbol = data.get("symbol", "BTCUSDT"),
            interval = data.get("interval", KlineIntervals.KLINE_INTERVAL_1MINUTE),
            limit = data.get("limit", 200)
        )