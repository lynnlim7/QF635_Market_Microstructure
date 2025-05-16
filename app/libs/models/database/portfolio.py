
from sqlalchemy import Column, Integer, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from libs.models.database import Base, FuturesPairs

__all__ = [
    "SpotPortfolio",
    "FuturesPortfolio",
    "Exposures",
]

class PortfolioMixin :
    __abstract__ = True 

    position_id = Column(Integer, primary_key=True, autoincrement=True)
    amount = Column(Numeric(precision=38, scale=10), nullable=False)

class SpotPortfolio(Base, PortfolioMixin) : 
    __tablename__ = "spot_portfolio"
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, unique=True)

class FuturesPortfolio(Base, PortfolioMixin) : 
    __tablename__ = "futures_portfolio"
    pair_id = Column(Integer, ForeignKey("futures_pairs.id"), nullable=False)
    average_price = Column(Numeric(precision=38, scale=10))
    leverage = Column(Numeric(precision=38, scale=10))

    pair = relationship("FuturesPairs", FuturesPairs.id, back_populates="id")

class Exposures(Base, PortfolioMixin) :
    __tablename__ = "exposures"
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)