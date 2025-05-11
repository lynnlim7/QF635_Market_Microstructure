from bot.portfolio.PortfolioManager import PortfolioManager


class RiskManager:
    def __init__(self, portfolio_manager:PortfolioManager,
                 max_risk_per_trade_pct:float =0.01):
        self.portfolio_manager = portfolio_manager
        self.max_risk_per_trade_pct = max_risk_per_trade_pct

    def calculate_position_size(self, entry_price, stop_loss_price):
        # Risk capital based on portfolio size
        capital = self.portfolio_manager.get_cash()
        risk_capital = capital * self.max_risk_per_trade_pct

        risk_per_unit = abs(entry_price - stop_loss_price)
        if risk_per_unit == 0:
            return 0  # Avoid division by zero

        position_size = risk_capital / risk_per_unit
        return position_size
