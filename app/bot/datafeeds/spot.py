from collections import deque
import redis.asyncio as redis
import asyncio
import websockets
import logging
import time
from bot.common.websockets import RawMultistreamMsg
import msgspec

from abc import ABC, abstractmethod
from typing import List

import itertools

RECONNECT_INTERVAL = 23.5 * 60 * 60

__all__ = [
    "KlineTask",
    "TradeTask",
    "SpotDataGateway",
    "BookTickerTask"
]


class TaskABC(ABC) : 
    @property
    @abstractmethod
    def refresh_tick(self) -> float : 
        pass

    @property
    def queue_size(self) -> int : 
        pass 

    @abstractmethod
    def get_subscriptions(self) -> List[str] : 
        pass

class TaskBase(TaskABC) :
    @property
    def refresh_tick(self) -> float : 
        return self._refresh_tick

    @refresh_tick.setter
    def refresh_tick(self, t) :
        self._refresh_tick = t

class KlineTask(TaskBase) :
    def __init__(self, symbols : List[str], intervals: List[str], refresh_tick:float=0.1) : 
        self._refresh_tick = refresh_tick
        self.symbols = symbols
        self.intervals = intervals

    @property
    def queue_size(self) -> int :
        return len(self.symbols) * len(self.intervals)
    
    def get_subscriptions(self) -> List[str] :
        out = []
        for sym, intv in itertools.product(self.symbols, self.intervals) : 
            out.append(f"{sym.lower()}@kline_{intv}")

        return out

class TradeTask(TaskBase) : 
    def __init__(self, symbols : List[str], agg : bool =True, refresh_tick:float =0.001) :
        self.refresh_tick = refresh_tick
        self.symbols = symbols
        self.agg = agg

    @property
    def queue_size(self) -> int :
        return len(self.symbols) * 10
    
    def get_subscriptions(self) -> List[str] :
        if self.agg :
            chan = "aggTrade"
        else :
            chan = "trade"
        
        out = [f"{symbol.lower()}@{chan}" for symbol in self.symbols]

        return out

class BookTickerTask(TaskBase) :
    def __init__(self, symbols : List[str], refresh_tick:float=0.001) : 
        self.symbols = symbols
        self.refresh_tick = refresh_tick

    @property
    def queue_size(self) -> int :
        return len(self.symbols) * 10

    def get_subscriptions(self) -> List[str] :
        out = [f"{symbol.lower()}@bookTicker" for symbol in self.symbols]
        return out


class SpotDataGateway :
    BASE_URL = "wss://stream.binance.com:9443"
    TESTNET_URL = "wss://ws-api.testnet.binance.vision/ws-api/v3"
    
    def __init__(self, 
                 redis_pool : redis.ConnectionPool, 
                 testnet: bool =False) : 
        r = redis.Redis.from_pool(redis_pool)
        if testnet :
            self.ws_url = self.TESTNET_URL
        else :
            self.ws_url = self.BASE_URL
        self._r = r
        self._q_idx = 0
        self._q = []

    async def init(self):
        await self._r.ping()
        logging.info("gateway connected to redis")

    async def register_task(self, task : TaskBase) :
        await self.init()
        retry = True
        self._q.append(deque(maxlen=task.queue_size))
        idx = self._q_idx
        self._q_idx+=1

        asyncio.create_task(self._start_update_redis(task, idx))
        while retry :
            try :
                retry = await asyncio.create_task(self._run_feed(task, idx))
            except Exception as e: 
                retry = False
                logging.error(e)
        logging.info("Task exited.")


    async def _run_feed(self, task : TaskBase, idx : int) -> bool :
        subscriptions = task.get_subscriptions()
        stream = self.ws_url + "/stream?streams=" + "/".join(subscriptions)
        async with websockets.connect(stream) as ws : 
            logging.info(f"gateway connected to binance connecting to streams {task.get_subscriptions()}")
            decoder = msgspec.json.Decoder(RawMultistreamMsg)
            start = time.time()
            while True : 
                try : 
                    ws_msg = await asyncio.wait_for(ws.recv(decode=False), timeout=120)
                    msg = decoder.decode(ws_msg)
                    key = f"spot:{msg.stream}"
                    self._q[idx].append((key, bytes(msg.data)))
                except asyncio.TimeoutError:
                    logging.info("[WS] Timeout – forcing reconnect")
                    break
                except websockets.ConnectionClosed as e:
                    logging.info(f"[WS] Closed: {e}")
                    break

                if time.time() - start > RECONNECT_INTERVAL:
                    logging.info("[WS] Reconnect interval reached – restarting connection")
                    return True
            return False

    async def _start_update_redis(self, task: TaskBase, idx : int) :
        r = self._r
        updates = {}
        q = self._q[idx]
        refresh_tick = task.refresh_tick
        pipe = r.pipeline(transaction=False)
        while True :
            start = time.time()
            while q :
                try :
                    k, v = q.popleft()
                    updates[k] = v
                except IndexError : 
                    break
                except Exception as e:
                    logging.error(e)
            if updates :
                pipe.mset(updates)
                for k, v in updates.items() : 
                    pipe.publish(k, v)
                await pipe.execute()
                await pipe.reset()
                updates.clear()
            elapsed = time.time() - start
            await asyncio.sleep(max(0, refresh_tick - elapsed))


