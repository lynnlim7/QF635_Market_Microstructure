import msgspec

class PortfolioStatsRequest(msgspec.Struct, gc=False, array_like=True) :
    symbol : str

class PortfolioPosition(msgspec.Struct, array_like=True) : 
    qty : float = 0.0
    average_price : float = 0.0
    
class PortfolioStatsResponse(msgspec.Struct, gc=False, array_like=True) : 
    position : PortfolioPosition
    unrealized_pnl : float = 0.0
    last_market_price : float = 0.0
    realized_pnl : float = 0.0 
    total_commissions : float = 0.0
    total_pnl : float = 0.0
    cash_balance : float = 0.0
    average_price : float = 0.0

    @classmethod
    def from_dict(cls, data) : 
        return cls(**data)
