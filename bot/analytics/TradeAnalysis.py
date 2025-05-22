import numpy as np
import pandas as pd
from math import sqrt

#step 1: implement function to calculate unrealized pnl, comparing with the latest P&L
#are we able to take unrealized pnl for different time ranges e.g. 1 day, 3 day, 5 day, 1 week
#step 2: calculate unrealized pnl using FIFO, LIFO, Weighted average cost
#include flash pnl?
#implement decision point on when to take the day cutoff for unrealised pnl calc need to fetch usdt price
#drawdown definition?

class TradeAnalysis:
    #initialize the params
    def __init__(self, trade_history: list, current_prices: dict= None):
        self.trade_history = trade_history
        self.df = pd.Dataframe(trade_history)
        self.current_prices = current_prices or {}

        #convert timestamps
        if 'timestamp' in self.df.columns:
            self.df = self.df.sort_values('timestamp')

    ###realized pnl###
    #calculate avg pnl of trades that are completed 

    def calculate_average_pnl(self):
        #Placeholder, change with how df looks later
        return self.df['pnl'].mean()
    
    ###unrealized pnl###
    ##can choose between FIFO or weighted average cost
    ##weighted average cost is better as we are doing HFT, tracking individual lots is impractical
    ###Include different time ranges as well e.g. '1D', '3D', '5D', '1W'
    def calculate_unrealized_pnl(self, time_range: str = None):
        #condition to guard against current prices not being provided
        if not self.current_prices:
            raise ValueError('Current prices not provided for unrealized PNL calculation')
        
        #Filter trades by time range if specified
        df = self.df.copy()
        if time_range:
            now = pd.Timestamp.now()
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
            

        #initialize values
        #group by asset to get current position sizes
        position_df = self.df.groupby('asset').agg({
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