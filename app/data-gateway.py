import yaml
import redis.asyncio as redis
import os
import asyncio
import logging

from bot.datafeeds import KlineTask, TradeTask, SpotDataGateway, BookTickerTask
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

async def init_spot_gateway(spot_subs, redis_params):
    spot_rpool = redis.ConnectionPool(
        db=0,
        max_connections=40,
        decode_responses=False,
        **redis_params
    )

    spot_gateway = SpotDataGateway(spot_rpool)

    if "kline" in spot_subs:
        symbols = spot_subs["kline"].get("symbols", [])
        intervals = spot_subs["kline"].get("intervals", [])
        if not symbols or not intervals:
            raise ValueError("Symbols or intervals not provided for kline task.")
        kline_task = KlineTask(symbols, intervals)
        asyncio.create_task(spot_gateway.register_task(kline_task))
    else:
        logging.info("No 'kline' subscription found in 'spot' section.")

    if "trade" in spot_subs:
        symbols = spot_subs["trade"].get("symbols", [])
        aggtradeTask = TradeTask(symbols, agg=True)
        tradeTask = TradeTask(symbols, agg=False)
        asyncio.create_task(spot_gateway.register_task(aggtradeTask))
        asyncio.create_task(spot_gateway.register_task(tradeTask))
    else:
        logging.info("No 'trade' subscription found in 'spot' section.")

    if "bookTicker" in spot_subs:
        symbols = spot_subs["bookTicker"].get("symbols", [])
        bookTickerTask = BookTickerTask(symbols)
        asyncio.create_task(spot_gateway.register_task(bookTickerTask))
    else:
        logging.info("No 'bookTicker' subscription found in 'spot' section.")


async def main():
    redis_params = {
        "host": os.getenv("REDIS_HOST", "localhost"),
        "password": os.getenv("REDIS_PASSWORD", None)
    }

    try:
        with open("subscriptions.yaml") as f:
            subdict = yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Failed to load subscription config: {e}")
        return

    if "spot" in subdict:
        await init_spot_gateway(subdict["spot"], redis_params)
    else:
        logging.warning("No 'spot' section found in subscriptions.yaml.")

    await asyncio.Event().wait() 

if __name__=="__main__" :
    asyncio.run(main())