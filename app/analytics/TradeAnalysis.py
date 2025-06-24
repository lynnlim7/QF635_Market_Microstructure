import numpy as np
import pandas as pd
from math import sqrt
import logging
import redis
import json
from typing import Dict, Any, Optional, List
from sqlalchemy import create_engine, text
from app.services.redis_pool import RedisPool
from app.services.redis_sub import RedisSubscriber
from app.utils.config import settings
from asyncio import new_event_loop, set_event_loop, run
from app.utils.func import get_execution_channel
import psycopg2
import time

#step 1: implement function to calculate unrealized pnl, comparing with the latest P&L
#are we able to take unrealized pnl for different time ranges e.g. 1 day, 3 day, 5 day, 1 week
#step 2: calculate unrealized pnl using FIFO, LIFO, Weighted average cost
#include flash pnl?
#implement decision point on when to take the day cutoff for unrealised pnl calc need to fetch usdt price
#drawdown definition?

logger = logging.getLogger(__name__)

def get_postgres_pool():
    pool = psycopg2.connect(
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
def listen_for_trades():
    logger.info("Starting trade listener...")

    pool = redis.ConnectionPool(host='redis', port=6379, decode_responses=True)
    channels = [get_execution_channel(settings.SYMBOL)]
    subscriber = RedisSubscriber(pool, channels)
    analysis = TradeAnalysis()

    def handle_execution(data: dict):
        logger.info(f"Received trade: {data}")
        try:
            analysis.handle_new_trade(data)
        except Exception as e:
            logger.error(f"Error processing trade: {e}")
    subscriber.register_handler(get_execution_channel(settings.SYMBOL), handle_execution)
    while True:
        try:
            subscriber.start_subscribing()
        except Exception as e:
            logger.error(f"Subscription error: {e}, reconnecting...")
            time.sleep(5) 

# # This function returns the summary
# def get_trade_summary():
#     pool = get_postgres_pool()
#     analysis = TradeAnalysis(db_pool=pool)
#     summary = analysis.get_summary()
#     return summary

# Main callable function from main.py
def run_trade_analysis():
    import threading
    thread = threading.Thread(target=listen_for_trades)
    thread.start()

class TradeAnalysis:
    #initialize the params
    def __init__(self, 
                 redis_params: Optional[Dict[str, Any]] = None,
                current_prices: Optional[Dict[str, float]]= None, use_db= True):
        self.redis_params = redis_params or {
            "host": settings.REDIS_HOST,
            "port": 6379,
            "db": 0,
            "decode_responses": False
        }
        if use_db:
            self.redis_pool = RedisPool(
        host=self.redis_params.get("host", "localhost"),
            port=self.redis_params.get("port", 6379),
            db=self.redis_params.get("db", 0),
            decode_responses=self.redis_params.get("decode_responses", False)  # Important: TradeAnalysis uses `redis.asyncio`
)
            self.engine = create_engine(
            f"postgresql://{settings.APP_PG_USER}:{settings.APP_PG_PASSWORD}@{settings.APP_PG_HOST}:{settings.APP_PG_PORT}/{settings.APP_PG_DB}"
        )
        else:
            self.engine = None
        self.redis = redis.Redis(connection_pool=self.redis_pool.pool)
        self.current_prices = current_prices or {}

        
        self.df = pd.DataFrame()
        
        #convert timestamps
        if 'timestamp' in self.df.columns:
            self.df = self.df.sort_values('timestamp')

    def fetch_current_prices_from_redis(self, symbols: List[str]) -> Dict[str,float]:
        if not self.redis_params:
            return {}
        r = self.redis
        prices = {}
        try:
            for symbol in symbols:
                # Try to get the most recent trade price first
                trade_key = f"spot:{symbol.lower()}@trade"
                trade_data = r.get(trade_key)
                
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
                book_data = r.get(book_key)
                
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
                kline_data = r.get(kline_key)
                
                if kline_data:
                    try:
                        kline = json.loads(kline_data.decode('utf-8'))
                        prices[symbol] = float(kline.get('c', kline.get('close', 0)))
                    except (json.JSONDecodeError, AttributeError, ValueError):
                        pass
                        
        finally:
            r.close()
        
        self.current_prices = prices
        return prices
    def fetch_trade_history_from_postgres(self):
        # pg_url = f"postgresql://{settings.APP_PG_USER}:{settings.APP_PG_PASSWORD}@{settings.APP_PG_HOST}:{settings.APP_PG_PORT}/{settings.APP_PG_DB}"
        # engine = create_engine(pg_url)
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SET search_path TO trading_app"))
                df = pd.read_sql("""SELECT 
                                 symbol, order_id, cum_filled_qty, avg_price, realized_pnl, last_price, last_qty, trade_time_ms, exec_type 
                FROM trading_app.futures_order 
                WHERE exec_type = 'TRADE';""", conn)
                numeric_cols = ['cum_filled_qty', 'avg_price', 'realized_pnl', 'last_price', 'last_qty']
                for col in numeric_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                if 'trade_time_ms' in df.columns:
                    df['trade_time_ms'] = pd.to_datetime(df['trade_time_ms'], unit='ms', errors='coerce')
                    df = df.dropna(subset=['trade_time_ms'])
            
                # Reset index to ensure clean indexing
                self.df = df.reset_index(drop=True)
            
                logger.info(f"Successfully fetched {len(df)} trades")
                if not df.empty:
                    logger.info(f"Latest trade: {df['trade_time_ms'].max()}")
        except Exception as e:
            logger.error(f"Error fetching trade history from Postgres: {e}")
            self.df = pd.DataFrame(columns=['symbol', 'realized_pnl', 'last_price', 'last_qty', 'trade_time_ms'])
    ###realized pnl###
    #calculate avg pnl of trades that are completed 

    def handle_new_trade(self, trade_data: dict):
        logger.info(f"[handle_new_trade] Processing new trade data...")
        # Refresh trade history from DB
        try:
            self.fetch_trade_history_from_postgres()

            # Update prices (you may optimize this later)
            self.fetch_current_prices_from_redis([trade_data.get("symbol", settings.SYMBOL)])

        # Recalculate summary
            print("\n" + "=" * 50)
            print("TRADE SUMMARY")
            print("=" * 50)
            print(f"Timestamp: {pd.Timestamp.now()}")
            print(f"Symbol: {trade_data.get('symbol')}")
            print(f"Trade ID: {trade_data.get('order_id')}")
            summary = self.get_summary(book_size=100000)


        
            # Also log the full summary
            logger.info(f"Trade Summary:\n{json.dumps(summary, indent=4)}")
        except Exception as e:
            logger.error(f"[handle_new_trade] Failed to calculate summary: {e}")

    def calculate_realized_pnl(self):
        try:
            if self.df.empty or 'realized_pnl' not in self.df.columns:
                return {'total_realized_pnl': 0, 'assets': {}}
            
            df = self.df.copy()
            df['realized_pnl'] = pd.to_numeric(df['realized_pnl'], errors='coerce').fillna(0)
            
            result = {'assets': {}, 'total_realized_pnl': 0}
            
            for symbol, group in df.groupby('symbol'):
                pnl_sum = group['realized_pnl'].sum()
                result['assets'][symbol] = {'realized_pnl': pnl_sum}
                result['total_realized_pnl'] += pnl_sum
                
            return result
        except Exception as e:
            logger.error(f"Realized PnL error: {str(e)}")
            return {'total_realized_pnl': 0, 'assets': {}}

    
    ###unrealized pnl###
    ##can choose between FIFO or weighted average cost
    ##weighted average cost is better as we are doing HFT, tracking individual lots is impractical
    ###Include different time ranges as well e.g. '1D', '3D', '5D', '1W' to look at trades done in previous day/week etc.
    def calculate_unrealized_pnl_from_orders(self, time_range: Optional[str] = None):
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
            self.fetch_current_prices_from_redis(symbols)

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
        try:
            if self.df.empty or 'realized_pnl' not in self.df.columns:
                return 0.0
            
            # Ensure we have valid data
            df = self.df.copy()
            df = df[df['realized_pnl'].notna()]
            
            if len(df) == 0:
                return 0.0
                
            wins = len(df[df['realized_pnl'] > 0])
            losses = len(df[df['realized_pnl'] < 0])
            
            if losses == 0:
                return 100.0 if wins > 0 else 0.0  # Cap at 100:1 ratio
            return min(wins / losses, 100.0)  # Still cap at 100 even with some losses
        except Exception as e:
            logger.error(f"Win/loss ratio error: {str(e)}")
            return 0.0

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
        peak = cumulative.expanding(min_periods=1).max()
        drawdown = (peak - cumulative) 
        max_drawdown_dollars = drawdown.max()

        max_drawdown_pct = (max_drawdown_dollars/ (0.5 * book_size) * 100)
        return max_drawdown_pct
    
    def calc_turnover (self, book_size: float) : 
        #Need the dollar trading value
        #booksize also a param
        try:
            if self.df.empty or book_size <= 0:
                return 0.0
                
            if 'last_price' not in self.df.columns or 'last_qty' not in self.df.columns:
                return 0.0
                
            df = self.df.copy()
            df['last_price'] = pd.to_numeric(df['last_price'], errors='coerce').fillna(0)
            df['last_qty'] = pd.to_numeric(df['last_qty'], errors='coerce').fillna(0)
            
            notional_value = (df['last_price'] * df['last_qty']).sum()
            return notional_value / book_size
        except Exception as e:
            logger.error(f"Turnover calculation error: {str(e)}")
            return 0.0

    def calc_fitness(self, book_size: float):
        sharpe_val = self.calc_sharpe_ratio()
        ret_val = pd.to_numeric(self.df['realized_pnl']).sum()
        turnover_val = self.calc_turnover(book_size)
        fit_val = sharpe_val * np.sqrt((abs(ret_val)/(max(turnover_val, 0.125))))
        return fit_val
    
    #additional function to load trades from separate source if required
    def load_trades_from_json(self, trades: List[Dict]):
        df = pd.DataFrame(trades)
        if 'trade_time_ms' in df.columns:
            df['trade_time_ms'] = pd.to_datetime(df['trade_time_ms'], unit='ms', errors='coerce')
            df = df.dropna(subset=['trade_time_ms'])
        self.df = df.reset_index(drop=True)

    #setting prices from best bid/ask
    def set_prices_from_best_bid_ask(self, best_bid_ask: Dict[str, Dict[str, float]]):
        self.current_prices = {}
        for symbol, prices in best_bid_ask.items():
            bid = prices.get("bid", 0)
            ask = prices.get("ask", 0)
            if bid > 0 and ask > 0:
                self.current_prices[symbol] = (bid + ask) / 2

    def get_summary(self, book_size: float = 100000, 
                    trades_json: Optional[List[Dict]] = None, best_bid_ask: Optional[Dict[str, Dict[str, float]]] = None):
        summary = {
        "win_loss_ratio": 0.0,
        "realized_pnl": {"total_realized_pnl": 0, "assets": {}},
        "unrealized_pnl": {"total_unrealized": 0, "assets": {}},
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "max_turnover": 0.0,
        "fitness": 0.0
        }
        try:
            #load trades if they are provided
            if trades_json:
                self.load_trades_from_json(trades_json)

            #fetch current prices if not already set
            if best_bid_ask:
                self.set_prices_from_best_bid_ask(best_bid_ask)

            print(self.df.head(5))
            summary["win_loss_ratio"] = self.calculate_win_loss_ratio()
            summary["realized_pnl"] = self.calculate_realized_pnl()
            summary["unrealized_pnl"] = self.calculate_unrealized_pnl_from_orders()
            summary["sharpe_ratio"] = self.calc_sharpe_ratio()
            summary["max_drawdown"] = self.calc_max_drawdown(book_size)
            summary["max_turnover"] = self.calc_turnover(book_size)
                
                # Calculate fitness safely
            try:
                ret_val = summary["realized_pnl"].get("total_realized_pnl", 0)
                turnover = max(summary["max_turnover"], 0.125)
                summary["fitness"] = summary["sharpe_ratio"] * sqrt(abs(ret_val)/turnover)
            except:
                summary["fitness"] = 0.0

                # Print to console (in addition to logging)


            print("-" * 50)
            print("Current Analytics")
            print("-" * 50)
            print(f"Win/Loss Ratio: {summary['win_loss_ratio']:.2f}")
            print(f"Realized PnL: {summary['realized_pnl']['total_realized_pnl']:.4f}")
            if 'BTCUSDT' in summary['realized_pnl']['assets']:
                print(f"BTCUSDT Realized: {summary['realized_pnl']['assets']['BTCUSDT']['realized_pnl']:.4f}")

            print(f"Unrealized PnL: {summary['unrealized_pnl']['total_unrealized']:.4f}")
            print(f"Sharpe Ratio: {summary['sharpe_ratio']:.2f}")
            print(f"Max Drawdown: {summary['max_drawdown']:.2f}%")
            print(f"Turnover: {summary['max_turnover']:.2f}x")
            print(f"Fitness Score: {summary['fitness']:.4f}")
            print("=" * 50 + "\n")


        except Exception as e:
            logger.error(f"Summary calculation error: {str(e)}")
        
        return summary
    
def main():

    # Initialize analyzer
    analyzer = TradeAnalysis()
    analyzer.fetch_trade_history_from_postgres()
    analyzer.start_price_listener(['BTCUSDT'])
    
    # Calculate PNL
    try:
        summary = analyzer.get_summary(book_size = 100000)
        print(f"Trade Summary: ")
        print(json.dumps(summary, indent=4))

    except ValueError as e:
        print(f"Error calculating Trade Summary: {e}")
if __name__ == "__main__":
    main()
    # Run the async main function
    # import asyncio
    # asyncio.run(main())