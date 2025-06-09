import numpy as np
import pandas as pd
from math import sqrt
import redis.asyncio as redis
import json
from typing import Dict, Any, Optional, List

#step 1: implement function to calculate unrealized pnl, comparing with the latest P&L
#are we able to take unrealized pnl for different time ranges e.g. 1 day, 3 day, 5 day, 1 week
#step 2: calculate unrealized pnl using FIFO, LIFO, Weighted average cost
#include flash pnl?
#implement decision point on when to take the day cutoff for unrealised pnl calc need to fetch usdt price
#drawdown definition?

class TradeAnalysis:
    #initialize the params
    def __init__(self, 
                 trade_history: list[Dict[str, Any]],
                 redis_params: Optional[Dict[str, Any]] = None,
                current_prices: Optional[Dict[str, float]]= None):
        self.trade_history = trade_history
        self.df = pd.DataFrame(trade_history)
        self.current_prices = current_prices or {}
        self.redis_params = redis_params or {
            "host": "localhost",
            "password": None,
            "db" : 0,
            "decode_responses": False
        }

        #convert timestamps
        if 'timestamp' in self.df.columns:
            self.df = self.df.sort_values('timestamp')

    async def fetch_current_prices_from_redis(self, symbols: List[str]) -> Dict[str,float]:
        if not self.redis_params:
            return {}
        r = redis.Redis(**self.redis_params)
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

    ###realized pnl###
    #calculate avg pnl of trades that are completed 

    def calculate_average_pnl(self):
        #Placeholder, change with how df looks later
        if self.df.empty:
            return {'total_unrealized_pnl': 0, 'assets': {}}
        # Convert to numeric types
        self.df['quantity'] = pd.to_numeric(self.df['quantity'])
        self.df['price'] = pd.to_numeric(self.df['price'])
        
        results = {'assets': {}, 'total_realized_pnl': 0}
        
        for asset, asset_df in self.df.groupby('asset'):

            # Weighted Average Cost method
            buys = asset_df[asset_df['quantity'] > 0]
            sells = asset_df[asset_df['quantity'] < 0]
            
            if buys.empty or sells.empty:
                continue
                
            # Calculate weighted average buy price
            total_buy_qty = buys['quantity'].sum()
            weighted_avg_buy = (buys['quantity'] * buys['price']).sum() / total_buy_qty
            
            # Calculate realized PnL for each sell trade
            realized_pnl = 0
            for _, sell in sells.iterrows():
                sell_qty = abs(sell['quantity'])
                sell_price = sell['price']
                
                # PnL = (Sell Price - Avg Buy Price) * Quantity Sold
                realized_pnl += (sell_price - weighted_avg_buy) * sell_qty
            
            results['assets'][asset] = {
                'realized_pnl': realized_pnl,
                'weighted_avg_cost': weighted_avg_buy,
                'total_bought': total_buy_qty,
                'total_sold': abs(sells['quantity'].sum())
            }
            results['total_realized_pnl'] += realized_pnl
 
        return results

    
    ###unrealized pnl###
    ##can choose between FIFO or weighted average cost
    ##weighted average cost is better as we are doing HFT, tracking individual lots is impractical
    ###Include different time ranges as well e.g. '1D', '3D', '5D', '1W' to look at trades done in previous day/week etc.
    async def calculate_unrealized_pnl(self, time_range: Optional[str] = None):

        if not self.current_prices:
            symbols = self.df['asset'].unique().tolist()
            await self.fetch_current_prices_from_redis(symbols)
        #condition to guard against current prices not being provided
        if not self.current_prices:
            raise ValueError('Current prices not provided for unrealized PNL calculation')
        
        #Filter trades by time range if specified
        df = self.df.copy()
        # Convert string timestamps to datetime (if not already)

        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        if time_range:
            now = pd.Timestamp.now(tz='UTC')
            if time_range == '6H':
                cutoff = now - pd.Timedelta(hours=6)
            elif time_range == '1D':
                cutoff = now - pd.Timedelta(days=1)
            elif time_range == '3D':
                cutoff = now - pd.Timedelta(days=3)
            elif time_range == '1W':
                cutoff = now - pd.Timedelta(weeks=1)
            else:
                raise ValueError(f"Unsupported time range: {time_range}")

            df = df[df['timestamp'] >= cutoff]
        
            # Debug: Print cutoff and timestamps
            print(f"[DEBUG] Cutoff: {cutoff}")
            print(f"[DEBUG] Oldest trade: {df['timestamp'].min()}")
        else:
            print(f"[DEBUG] No time range applied; using all trades")
        #initialize values
        #group by asset to get current position sizes
        position_df = df.groupby('asset').agg({
            'quantity': 'sum',
            'price' : 'mean'
        }).reset_index()

        results = {'assets': {}, 'total_unrealized' : 0}

        for _, row in position_df.iterrows():
            asset = row['asset']
            quantity = row['quantity']

            if quantity == 0:
                continue
            
            if asset not in self.current_prices:
                raise ValueError(f"Current price not availabe for asset: {asset}")
            
            current_price = self.current_prices[asset]
            avg_entry_price = row['price']
            unrealized = (current_price - avg_entry_price) * quantity

            results['assets'][asset] = {
                'quantity': quantity,
                'entry_price': avg_entry_price,
                'current_price': current_price,
                'unrealized_pnl': unrealized
            }
            
            results['total_unrealized'] += unrealized
            
        return results            

    #calculate win and losses
    def calculate_win_loss_ratio(self):
        wins =  len(self.df[self.df['pnl'] > 0] )
        losses = len(self.df[self.df['pnl'] > 0] )
        return wins / losses if losses else float('inf')

    #only used for realized pnl
    def calc_sharpe_ratio(self, risk_free_rate =0.0):
        if len(self.df) < 2:
            return 0.0
        returns = self.df['pnl']
        #placeholder
        avg_return = returns.mean()
        std_dev = returns.std()

        #use this if pnl is per-trade
        sharpe_ratio = (avg_return - risk_free_rate) / std_dev

        #use this if pnl is daily returns
        #sharpe_ratio = sqrt(252) * ((avg_return - risk_free_rate) / std_dev)

        return sharpe_ratio

    def calc_max_drawdown (self, book_size: float):

        cumulative = self.df['pnl'].cumsum()
        peak = cumulative.expanding(min_period=1).max()
        drawdown = (peak - cumulative) 
        max_drawdown_dollars = drawdown.max()

        max_drawdown_pct = (max_drawdown_dollars/ (0.5 * book_size) * 100)
        return max_drawdown_pct
    
    def calc_turnover (self, book_size: float) : 
        #Need the dollar trading value
        #booksize also a param
        total_trade = (self.df['quantity'].abs() * self.df['price'].sum()) / book_size
        return total_trade

    def calc_fitness(self):
        sharpe_val = self.calc_sharpe_ratio()
        ret_val = self.df['pnl'].cumsum()
        turnover_val = self.calc_turnover()
        fit_val = sharpe_val * np.sqrt((abs(ret_val)/(max(turnover_val, 0.125))))
        return fit_val

    def get_summary(self):
        return {
            "win_loss_ratio": self.calculate_win_loss_ratio(),
            "average_pnl": self.calculate_average_pnl(),
            "sharpe_ratio": self.calc_sharpe_ratio(),
            "max_drawdown": self.calc_max_drawdown(),
            "max_turnover": self.calc_turnover(),
            "fitness": self.calc_fitness            
        }
    
async def main():
    # Your trade history data
    trade_history = [
        {'asset': 'BTCUSDT', 'quantity': 1.0, 'price': 99000, 'timestamp': '2025-05-26'},
        {'asset': 'ADAUSDT', 'quantity': 1000, 'price': 0.35, 'timestamp': '2023-01-02'},
        {'asset': 'ETHUSDT', 'quantity': 5, 'price': 3500, 'timestamp': pd.Timestamp.now().strftime('%Y-%m-%d')}
    ]
    
    # Redis connection params (same as your gateway)
    redis_params = {
        "host": "localhost",
        "password": None,
        "db": 0
    }
    
    # Initialize analyzer
    analyzer = TradeAnalysis(trade_history, redis_params=redis_params)
    
    # Calculate PNL
    try:
        unrealized_pnl = await analyzer.calculate_unrealized_pnl('1D')
        #realized_pnl = analyzer.calculate_average_pnl()
        print(f"Unrealized PNL: {unrealized_pnl}")
        #print(f"Realized PNL: {realized_pnl}")
    except ValueError as e:
        print(f"Error calculating PNL: {e}")

# Run the async main function
import asyncio
asyncio.run(main())