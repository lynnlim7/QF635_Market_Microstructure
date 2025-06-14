import httpx
import zipfile
from datetime import datetime, timezone, timedelta
import pandas as pd
from io import BytesIO
import time
import pytz
import os
from typing import List
from tqdm import tqdm

LOCAL_TZ = pytz.timezone("Asia/Singapore")

FUTURES_URL_TEMPLATE = "https://data.binance.vision/data/futures/um/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{date_str}.zip"

def download_historical(symbols : List[str], interval : List[str], days_ago=180) :
    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
        "ignore"
    ]

    daterange_end = datetime.now(LOCAL_TZ).astimezone(timezone.utc) - timedelta(minutes=60 * 30) # Data delivered around 3-4am UTC
    daterange_start = daterange_end - timedelta(days=days_ago)
    
    extract_dates = [date.date().strftime("%Y-%m-%d") for date in pd.date_range(start=daterange_start, end=daterange_end)]

    for symbol in symbols :
        symbol_dir = f"./historical/futures_klines_{interval}/{symbol}/"
        os.makedirs(symbol_dir, exist_ok=True)
        for dt in tqdm(extract_dates) :
            url = FUTURES_URL_TEMPLATE.format(symbol=symbol, date_str=dt, interval=interval)
            target_file = symbol_dir + f"{dt.replace('-','')}.parquet"
            if os.path.exists(target_file) :
                continue
            response = httpx.get(url)
            response.raise_for_status()

            with zipfile.ZipFile(BytesIO(response.content)) as z:
                # There should be only one file inside the zip
                csv_filename = z.namelist()[0]

                with z.open(csv_filename) as f:
                    df = pd.read_csv(f, names=columns, skiprows=1)
                    df = df[df["ignore"] != 1]
                    df.drop("ignore", axis=1, inplace=True)
                    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
                    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
                    df["date"] = pd.to_datetime(dt)
                    df.to_parquet(target_file, index=False)

            time.sleep(0.2)