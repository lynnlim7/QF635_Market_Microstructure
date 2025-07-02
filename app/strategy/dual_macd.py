import pandas as pd
import numpy as np
# from binance import Client

# from app.api.binance_api import BinanceApi
import backtrader as bt
from datetime import datetime
from app.utils.config import settings
import datetime as datetime

# from app.utils.logger import setup_logger
# from typing import Callable, List
# from app.utils.logger import main_logger

class DualMACD(bt.Strategy):
    # MACD params 
    params = (
        ('fast_macd_fast', 8),
        ('fast_macd_slow', 17),
        ('fast_macd_signal', 9),
        ('slow_macd_fast', 12),
        ('slow_macd_slow', 26),
        ('slow_macd_signal', 9),
    )

    def __init__(self):
        # fast MACD (3,10,16)
        self.macd_fast = bt.indicators.MACD(self.data.close,
                                period_me1=self.p.fast_macd_fast,
                                period_me2=self.p.fast_macd_slow,
                                period_signal=self.p.fast_macd_signal
                                )

        # slow MACD (12,26,9)
        self.macd_slow = bt.indicators.MACD(self.data.close,
                                period_me1=self.p.slow_macd_fast,
                                period_me2=self.p.slow_macd_slow,
                                period_signal=self.p.slow_macd_signal
                                )

        print(f"Dual MACD Strategy initialized")

        self.fast_crossover = bt.indicators.CrossOver(self.macd_fast.macd, self.macd_fast.signal)
        self.slow_crossover = bt.indicators.CrossOver(self.macd_slow.macd, self.macd_slow.signal)
        
    def next(self):
        print(f"{self.datetime.datetime(0)} - Price: {self.data.close[0]}")
        self.buy_signal = False
        self.sell_signal = False

        # keep short-term memory (e.g. 3 bars back)
        if self.fast_crossover[0] > 0 or self.fast_crossover[-1] > 0 or self.fast_crossover[-2] > 0:
            if self.slow_crossover[0] > 0 or self.slow_crossover[-1] > 0 or self.slow_crossover[-2] > 0:
                self.buy_signal = True
                # if self.fast_crossover > 0 and self.slow_crossover > 0:
                #     if not self.position:
                #         self.buy()
        if not self.position and self.buy_signal:
            self.buy()
        elif self.position and self.sell_signal:
            self.close()

        
        # elif self.fast_crossover < 0 or self.slow_crossover < 0:
        #     if self.position:
        #         self.sell()

        


                

        
