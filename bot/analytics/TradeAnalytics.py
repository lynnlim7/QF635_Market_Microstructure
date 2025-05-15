class TradeAnalytics:
    def __init__(self, trade_history: list):
        self.trade_history = trade_history

    def calculate_win_loss_ratio(self):
        wins = [t for t in self.trade_history if t["pnl"] > 0]
        losses = [t for t in self.trade_history if t["pnl"] <= 0]
        return len(wins) / len(losses) if losses else float('inf')

    def calculate_average_pnl(self):
        return sum(t["pnl"] for t in self.trade_history) / len(self.trade_history)



    def get_summary(self):
        return {
            "win_loss_ratio": self.calculate_win_loss_ratio(),
            "average_pnl": self.calculate_average_pnl(),
        }
