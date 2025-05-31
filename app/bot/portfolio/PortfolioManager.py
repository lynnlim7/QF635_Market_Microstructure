


class PortfolioManager:
    def __init__(self, starting_cash: float = 10000.0):
        self.cash = starting_cash
        self.positions = {}  # {symbol: {"qty": float, "entry_price": float}}
        self.realized_pnl = 0.0
        self.open_trades = []
        self.trade_history = []

    # Position Updates
    def buy(self, symbol, qty, price):
        cost = qty * price
        if self.cash < cost:
            raise ValueError("Not enough cash")
        self.cash -= cost
        pos = self.positions.get(symbol, {"qty": 0.0, "entry_price": 0.0})
        new_qty = pos["qty"] + qty
        avg_price = ((pos["qty"] * pos["entry_price"]) + (qty * price)) / new_qty
        self.positions[symbol] = {"qty": new_qty, "entry_price": avg_price}

    def sell(self, symbol, qty, price):
        if symbol not in self.positions or self.positions[symbol]["qty"] < qty:
            raise ValueError("Not enough position")
        entry_price = self.positions[symbol]["entry_price"]
        pnl = (price - entry_price) * qty
        self.realized_pnl += pnl
        self.cash += qty * price
        remaining_qty = self.positions[symbol]["qty"] - qty
        if remaining_qty <= 0:
            del self.positions[symbol]
        else:
            self.positions[symbol]["qty"] = remaining_qty

    # State Accessors
    def get_cash(self):
        return self.cash

    def get_positions(self):
        return self.positions

    def get_realized_pnl(self):
        return self.realized_pnl

    def get_unrealized_pnl(self, current_prices: dict):
        pnl = 0.0
        for sym, pos in self.positions.items():
            if sym in current_prices:
                market_price = current_prices[sym]
                pnl += (market_price - pos["entry_price"]) * pos["qty"]
        return pnl

    def get_total_portfolio_value(self, current_prices: dict):
        return self.cash + self.get_unrealized_pnl(current_prices)

    def get_summary(self, current_prices: dict = None):
        summary = {
            "cash": self.cash,
            "positions": self.positions,
            "realized_pnl": self.realized_pnl,
        }
        if current_prices:
            summary["unrealized_pnl"] = self.get_unrealized_pnl(current_prices)
            summary["total_value"] = self.get_total_portfolio_value(current_prices)
        return summary