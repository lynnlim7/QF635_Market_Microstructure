import numpy as np
import pandas as pd
from math import sqrt
import logging
import redis.asyncio as redis
import json
from typing import Dict, Any, Optional, List
from sqlalchemy import create_engine
import asyncpg
from app.services.redis_pool import RedisPool
from app.services.redis_sub import RedisSubscriber
from app.utils.config import settings

#step 1: implement function to calculate unrealized pnl, comparing with the latest P&L
#are we able to take unrealized pnl for different time ranges e.g. 1 day, 3 day, 5 day, 1 week
#step 2: calculate unrealized pnl using FIFO, LIFO, Weighted average cost
#include flash pnl?
#implement decision point on when to take the day cutoff for unrealised pnl calc need to fetch usdt price
#drawdown definition?

logger = logging.getLogger(__name__)

async def get_postgres_pool():
    pool = await asyncpg.create_pool(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        min_size=1,
        max_size=10
    )
    return pool

# Background listener to DB updates from Redis
async def listen_for_trades():
    logger.info("Starting trade listener...")
    subscriber = RedisSubscriber([f"{settings.SYMBOL.lower()}:execution"])
    analysis = TradeAnalysis()

    async def handle_execution(data: dict):
        logger.info(f"Received trade: {data}")
        try:
            await analysis.handle_new_trade(data)
        except Exception as e:
            logger.error(f"Error processing trade: {e}")

    subscriber.register_async_handler(f"{settings.SYMBOL.lower()}:execution", handle_execution)
    await subscriber.start_async_subscribing()

# This function returns the summary
async def get_trade_summary():
    pool = await get_postgres_pool()
    analysis = TradeAnalysis(db_pool=pool)
    summary = await analysis.get_summary()
    return summary

# Main callable function from main.py
def run_trade_analysis():
    loop = asyncio.get_event_loop()
    loop.create_task(listen_for_trades())

class TradeAnalysis:
    #initialize the params
    def __init__(self, 
                 redis_params: Optional[Dict[str, Any]] = None,
                current_prices: Optional[Dict[str, float]]= None):

        self.current_prices = current_prices or {}
        self.redis_pool = RedisPool(
        host=redis_params.get("host", "localhost"),
            port=redis_params.get("port", 6379),
            db=redis_params.get("db", 0),
            decode_responses=redis_params.get("decode_responses", False),
            async_pool=True  # Important: TradeAnalysis uses `redis.asyncio`
)
        self.redis = redis.Redis(connection_pool=self.redis_pool.pool)
        self.df = pd.DataFrame()

        #convert timestamps
        if 'timestamp' in self.df.columns:
            self.df = self.df.sort_values('timestamp')

    async def fetch_current_prices_from_redis(self, symbols: List[str]) -> Dict[str,float]:
        if not self.redis_params:
            return {}
        r = self.redis
        prices = {}
        try:
            for symbol in symbols:
                # Try to get the most recent trade price first
                trade_key = f"spot:{symbol.lower()}@trade"
                trade_data = await r.get(trade_key)
                
                if trade_data:
                    try:
                        # Parse the trade data (adjust based on actual format)
                        trade = json.loads(trade_data.decode('utf-8'))
                        prices[symbol] = float(trade.get('p', trade.get('price', 0)))
                        continue
                    except (json.JSONDecodeError, AttributeError, ValueError):
                        pass
                
                # Fallback to bookTicker if trade not available
                book_key = f"spot:{symbol.lower()}@bookTicker"
                book_data = await r.get(book_key)
                
                if book_data:
                    try:
                        book = json.loads(book_data.decode('utf-8'))
                        # Use average of bid and ask as current price
                        bid = float(book.get('b', book.get('bidPrice', 0)))
                        ask = float(book.get('a', book.get('askPrice', 0)))
                        prices[symbol] = (bid + ask) / 2
                        continue
                    except (json.JSONDecodeError, AttributeError, ValueError):
                        pass
                
                # Final fallback to kline close price
                kline_key = f"spot:{symbol.lower()}@kline_1m"  # Using 1m interval
                kline_data = await r.get(kline_key)
                
                if kline_data:
                    try:
                        kline = json.loads(kline_data.decode('utf-8'))
                        prices[symbol] = float(kline.get('c', kline.get('close', 0)))
                    except (json.JSONDecodeError, AttributeError, ValueError):
                        pass
                        
        finally:
            await r.close()
        
        self.current_prices = prices
        return prices
    def fetch_trade_history_from_postgres(self):
        pg_url = f"postgresql://{settings.APP_PG_USER}:{settings.APP_PG_PASSWORD}@{settings.APP_PG_HOST}:{settings.APP_PG_PORT}/{settings.APP_PG_DB}"
        engine = create_engine(pg_url)

        query = "SELECT * FROM futures_order WHERE exec_type = 'TRADE';"
        df = pd.read_sql(query, engine)
        df = df.sort_values('timestamp')
        self.df = df
    ###realized pnl###
    #calculate avg pnl of trades that are completed 

    def calculate_realized_pnl(self):
        #Placeholder, change with how df looks later
        if self.df.empty or 'exec_type' not in self.df.columns:
            return {'total_realized_pnl': 0, 'assets': {}}
        
        df = self.df.copy()
        df = df[df['exec_type'] == 'TRADE']
        df['realized_pnl'] = pd.to_numeric(df['realized_pnl'])

        results = {'assets': {}, 'total_realized_pnl': 0}

        for symbol, group in df.groupby('symbol'):
            pnl_sum = group['realized_pnl'].sum()
            results['assets'][symbol] = {'realized_pnl': pnl_sum}
            results['total_realized_pnl'] += pnl_sum

        return results

    
    ###unrealized pnl###
    ##can choose between FIFO or weighted average cost
    ##weighted average cost is better as we are doing HFT, tracking individual lots is impractical
    ###Include different time ranges as well e.g. '1D', '3D', '5D', '1W' to look at trades done in previous day/week etc.
    async def calculate_unrealized_pnl_from_orders(self, time_range: Optional[str] = None):
        if self.df.empty or 'exec_type' not in self.df.columns:
            return {'total_unrealized': 0, 'assets': {}}

        df = self.df.copy()
        df = df[df['exec_type'] == 'TRADE']
        df['cum_filled_qty'] = pd.to_numeric(df['cum_filled_qty'])
        df['avg_price'] = pd.to_numeric(df['avg_price'])

        df['trade_time_ms'] = pd.to_datetime(df['trade_time_ms'], unit='ms')
        if time_range:
            cutoff = pd.Timestamp.now(tz='UTC') - pd.Timedelta(time_range)
            df = df[df['trade_time_ms'] >= cutoff]

        positions = df.groupby('symbol').agg({
            'cum_filled_qty': 'sum',
            'avg_price': 'mean'
        }).reset_index()

        if not self.current_prices:
            symbols = positions['symbol'].tolist()
            await self.fetch_current_prices_from_redis(symbols)

        results = {'assets': {}, 'total_unrealized': 0}
        for _, row in positions.iterrows():
            symbol = row['symbol']
            qty = row['cum_filled_qty']
            avg_price = row['avg_price']

            if symbol not in self.current_prices:
                raise ValueError(f"Missing current price for {symbol}")
            current_price = self.current_prices[symbol]

            unrealized = (current_price - avg_price) * qty

            results['assets'][symbol] = {
                'quantity': qty,
                'entry_price': avg_price,
                'current_price': current_price,
                'unrealized_pnl': unrealized
            }
            results['total_unrealized'] += unrealized

        return results
    def start_price_listener(self, symbols: List[str]):
        def update_price_callback(data: dict):
            symbol = data.get("s")
            price = float(data.get("p", 0))
            self.current_prices[symbol] = price

        topics = [f"spot:{symbol.lower()}@trade" for symbol in symbols]
        subscriber = RedisSubscriber.from_pool(self.redis_pool.pool, topics)
        for topic in topics:
            subscriber.register_handler(topic, update_price_callback)
        subscriber.start_subscribing()

    #calculate win and losses
    def calculate_win_loss_ratio(self):
        if 'realized_pnl' not in self.df.columns:
            return 0.0

        self.df['realized_pnl'] = pd.to_numeric(self.df['realized_pnl'])
        wins =  len(self.df[self.df['realized_pnl'] > 0] )
        losses = len(self.df[self.df['realized_pnl'] > 0] )
        if losses == 0:
            return float('inf') if wins > 0 else 0.0
        return wins / losses 

    #only used for realized pnl
    def calc_sharpe_ratio(self, risk_free_rate =0.0):
        if len(self.df) < 2:
            return 0.0
        returns = pd.to_numeric(self.df['realized_pnl'])
        #placeholder
        avg_return = returns.mean()
        std_dev = returns.std()

        #use this if pnl is per-trade
        sharpe_ratio = (avg_return - risk_free_rate) / std_dev

        #use this if pnl is daily returns
        #sharpe_ratio = sqrt(252) * ((avg_return - risk_free_rate) / std_dev)

        return sharpe_ratio

    def calc_max_drawdown (self, book_size: float):

        cumulative = pd.to_numeric(self.df['realized_pnl']).cumsum()
        peak = cumulative.expanding(min_period=1).max()
        drawdown = (peak - cumulative) 
        max_drawdown_dollars = drawdown.max()

        max_drawdown_pct = (max_drawdown_dollars/ (0.5 * book_size) * 100)
        return max_drawdown_pct
    
    def calc_turnover (self, book_size: float) : 
        #Need the dollar trading value
        #booksize also a param
        self.df['last_price'] = pd.to_numeric(self.df['last_price'], errors='coerce')
        self.df['last_qty'] = pd.to_numeric(self.df['last_qty'], errors='coerce')

        notional_value = (self.df['last_price'] * self.df['last_qty']).sum()
        turnover = notional_value / book_size
        return turnover

    def calc_fitness(self, book_size: float):
        sharpe_val = self.calc_sharpe_ratio()
        ret_val = pd.to_numeric(self.df['realized_pnl']).sum()
        turnover_val = self.calc_turnover(book_size)
        fit_val = sharpe_val * np.sqrt((abs(ret_val)/(max(turnover_val, 0.125))))
        return fit_val

    async def get_summary(self, book_size: float = 100000):
        return {
            "win_loss_ratio": self.calculate_win_loss_ratio(),
            "realized_pnl": self.calculate_realized_pnl(),
            "unrealized_pnl": self.calculate_unrealized_pnl_from_orders(),
            "sharpe_ratio": self.calc_sharpe_ratio(),
            "max_drawdown": self.calc_max_drawdown(book_size),
            "max_turnover": self.calc_turnover(book_size),
            "fitness": self.calc_fitness(book_size)            
        }
    
async def main():

    # Initialize analyzer
    analyzer = TradeAnalysis()
    analyzer.fetch_trade_history_from_postgres()
    analyzer.start_price_listener(['BTCUSDT'])
    
    # Calculate PNL
    try:
        summary = await analyzer.get_summary(book_size = 100000)
        print(f"Trade Summary: ")
        print(json.dumps(summary, indent=4))

    except ValueError as e:
        print(f"Error calculating Trade Summary: {e}")
if __name__ == "__main__":
    # Run the async main function
    import asyncio
    asyncio.run(main())