

import pandas as pd
import time

from app.analytics.TradeAnalysis import TradeAnalysis
from app.api.base_gateway import BaseGateway
from app.common.interface_book import OrderBook, PriceLevel
from app.utils.func import get_candlestick_channel, get_orderbook_channel
from app.utils.logger import main_logger as logger
import asyncio
import os
from threading import Thread
"""
Mock Gateway
"""

# config

SIMULATION_TIME_IN_MINUTES = 30
# if u want to cut data into half -> put 1/2
DATA_RATIO = 1

CANDLESTICK_FILE_NAME = "BTCUSDT-1m-2024-03-30.csv"
ORDERBOOK_FILE_NAME = "BTCUSDT_240927-bookTicker-2024-03-30.csv"


class MockBinanceGateway(BaseGateway):
    def __init__(self, symbol:str, redis_publisher = None):
        logger.info("INSTANTIATING MOCK GATEWAY")
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self._symbol = symbol.lower()
        self.publisher = redis_publisher

        # loop and dedicated thread to run all async concurrent tasks
        self._loop = asyncio.new_event_loop()
        self._loop_thread = Thread(target=self._run_async_tasks, daemon=True, name="MockBinanceGateway")

        self.orderbook = pd.DataFrame()
        self.orderbook_list: list[dict] = []
        self.candlestick_list: list[dict] = []
        self.candlestick: pd.DataFrame = pd.DataFrame()
        self.candlestick_time_ratio = 1

        self.trade_analysis = TradeAnalysis()

        self.load_data()

    def _run_async_tasks(self):
        """ Run the following tasks concurrently in the current thread """
        self._loop.create_task(self.produce_candlestick())
        self._loop.create_task(self.produce_orderbook())
        self._loop.run_forever()

    def connection(self):
        logger.info("Initialising mock connection")
        time.sleep(2)
        self._loop_thread.start()



    def load_data(self):
        simulation_time_ms = SIMULATION_TIME_IN_MINUTES * 60 * 1000


        logger.info("Loading mock candlestick data")
        self.candlestick = pd.read_csv(f"{self.base_dir}/data/{CANDLESTICK_FILE_NAME}")

        sliced = len(self.candlestick) // int((1 / DATA_RATIO))
        print("sliced")
        self.candlestick = self.candlestick.iloc[:sliced].copy()
        self.candlestick['time_elapsed_ms'] =  self.candlestick['open_time'].shift(-1) -  self.candlestick['open_time']

        # presave the list first
        for index, row in self.candlestick.iterrows():
            self.candlestick_list.append(self.to_candlestick(row))


        first_row =  self.candlestick.iloc[0]
        last_row =  self.candlestick.iloc[-1]

        last_row_timing = last_row['close_time']

        total_time_elapsed_ms = last_row['close_time'] - first_row['close_time']
        time_ratio = simulation_time_ms / total_time_elapsed_ms
        self.candlestick['simulation_sleep_time_ms'] =  self.candlestick['time_elapsed_ms'].apply(lambda x: x * time_ratio)

        logger.info(f"Done loading candlestick data: size: {len(self.candlestick)}, time_ratio = {time_ratio}")


        logger.info("Loading mock orderbook data")

        orderbook_df =  pd.read_csv(f"{self.base_dir}/data/{ORDERBOOK_FILE_NAME}")
        # Resample best_bid / best_ask every 1s
        orderbook_df['transaction_time'] = pd.to_datetime(orderbook_df['transaction_time'], unit='ms')
        resampled_df = (
            orderbook_df.set_index('transaction_time')
            .resample('20s')
            .agg({'best_bid_price': 'last', 'best_bid_qty': 'last', 'best_ask_price': 'last', 'best_ask_qty': 'last',
                  'update_id': 'last', 'event_time': 'last'})
            .dropna()
            .reset_index()
        )


        self.orderbook = resampled_df[resampled_df['event_time'] < last_row_timing]

        # TODO: not good design, create object then throw away, fix this
        for index, row in self.orderbook.iterrows():
            orderbook_obj = OrderBook(
                timestamp=float(row['event_time']),
                contract_name='BTCUSDT',
                bids=[PriceLevel(
                    price=float(row['best_bid_price']),
                    size=float(row['best_bid_qty']),
                    quote_id=str(row['update_id'])
                )],
                asks=[PriceLevel(
                    price=float(row['best_ask_price']),
                    size=float(row['best_ask_qty']),
                    quote_id=str(row['update_id'])
                )]
            )
            self.orderbook_list.append(orderbook_obj.to_dict())

        self.orderbook['time_elapsed_ms'] = (
            resampled_df['transaction_time'].shift(-1) - resampled_df['transaction_time']
        ).dt.total_seconds() * 1000

        ob_first_row = self.orderbook.iloc[0]
        ob_last_row = self.orderbook.iloc[-1]
        ob_total_time_elapsed_ms = (
           ob_last_row['transaction_time'] - ob_first_row['transaction_time']
        ).total_seconds() * 1000
        ob_time_ratio = simulation_time_ms / ob_total_time_elapsed_ms
        self.orderbook['simulation_sleep_time_ms'] = self.orderbook['time_elapsed_ms'].apply(lambda x: x * ob_time_ratio)

        logger.info(f"Done loading orderbook data: size: {len(self.orderbook)}, time_ratio = {ob_time_ratio}")


    async def produce_candlestick(self):

        total_rows = len(self.candlestick)
        num_checkpoints = 20  # for 5% intervals
        # Precompute checkpoint indices
        checkpoint_indices = {
            int((i / num_checkpoints) * total_rows) - 1  # -1 because idx is 0-based
            for i in range(1, num_checkpoints + 1)
        }

        candlestick_channel = None
        if self.publisher:
            candlestick_channel = get_candlestick_channel(self._symbol)

        # loop through candlestick
        for index, (_,row) in enumerate(self.candlestick.iterrows()):
            sleep_time_ms = row['simulation_sleep_time_ms']
            await asyncio.sleep(sleep_time_ms / 1_000)

            if candlestick_channel:
                candlestick = self.candlestick_list[index]
                self.publisher.publish(candlestick_channel, candlestick)

            if index in checkpoint_indices:
                percent_complete = int(((index + 1) / total_rows) * 100)
                logger.info(f"Candlestick production {percent_complete}% complete.")
        # lop through order book
        pass

    async def produce_orderbook(self):
        logger.info(f"Producing orderbook data now! {self.publisher}")

        # this section is just to tract prograss
        total_rows = len(self.orderbook)
        num_checkpoints = 20  # for 10% intervals
        # Precompute checkpoint indices
        checkpoint_indices = {
            int((i / num_checkpoints) * total_rows) - 1  # -1 because idx is 0-based
            for i in range(1, num_checkpoints + 1)
        }

        orderbook_channel = None
        if self.publisher:
            orderbook_channel = get_orderbook_channel(self._symbol)


        # Ensure last index is included
        checkpoint_indices.add(total_rows - 1)
        for idx, (_, row) in enumerate(self.orderbook.iterrows()):
            sleep_time_ms = row['simulation_sleep_time_ms']
            await asyncio.sleep(sleep_time_ms / 1_000)

            if orderbook_channel:
                # orderbook_channel = get_orderbook_channel(self._symbol)
                curr_ob = self.orderbook_list[idx]
                # logger.info(f"sending order book data {curr_ob['timestamp']}")
                self.publisher.publish(orderbook_channel, curr_ob)

            if idx in checkpoint_indices:
                percent_complete = int(((idx + 1) / total_rows) * 100)
                logger.info(f"Orderbook production {percent_complete}% complete.")

        # once done with publishing all, just generate statistics
        logger.info(f"Done with order book! {self.publisher}")
        if self.publisher:
            logger.info("Printing the last signal now!!!")
            orderbook_channel = get_orderbook_channel(self._symbol)
            orderbook_obj = OrderBook(
                timestamp=float(-1),
                contract_name='BTCUSDT',
                bids=[],
                asks=[]
            )
            self.publisher.publish(orderbook_channel, orderbook_obj.to_dict())
        pass



    def to_candlestick(self, row: pd.Series) -> dict:
        return {
            "symbol": 'BTCUSDT',
            "interval": '1m',
            "open": float(row['open']),
            "close": float(row['close']),
            "high": float(row['high']),
            "low": float(row['low']),
            "volume": float(row['volume']),
            "is_closed": bool(True),
            "start_time": int(row['open_time']),
            "end_time": int(row['close_time']),
            "source": "candlestick"
        }


if __name__=="__main__" :

    temp = MockBinanceGateway(symbol='BTCUSDT', redis_publisher=None)
    temp.connection()

    while True:
        i = 0
