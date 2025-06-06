
from sqlalchemy import Column, Integer, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from models import Base

__all__ = [
    "SpotPortfolio",
    "FuturesPositions",
    "Exposures",
    "FuturesWallet"
]

class PortfolioMixin :
    __abstract__ = True 

    position_id = Column(Integer, primary_key=True, autoincrement=True)
    amount = Column(Numeric(precision=38, scale=10), nullable=False)

class SpotPortfolio(Base, PortfolioMixin) : 
    __tablename__ = "spot_portfolio"
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, unique=True)
    asset = relationship("Assets")

class FuturesPositions(Base, PortfolioMixin) : 
    __tablename__ = "futures_positions"
    pair_id = Column(Integer, ForeignKey("futures_pairs.id"), nullable=False, unique=True)
    average_price = Column(Numeric(precision=38, scale=10))
    leverage = Column(Numeric(precision=38, scale=10))

    pair = relationship("FuturesPairs")

class FuturesWallet(Base, PortfolioMixin) :
    __tablename__ = "futures_wallet"
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, unique=True)
    asset = relationship("Assets")

class Exposures(Base, PortfolioMixin) :
    __tablename__ = "exposures"
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)