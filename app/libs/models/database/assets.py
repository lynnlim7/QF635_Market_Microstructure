
from sqlalchemy import Column, Integer, Boolean, String, DateTime, Numeric, Index, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import relationship
from libs.models.database import Base

__all__ = [
    "Assets",
    "SpotPairs",
    "FuturesPairs",
]

class Assets(Base) : 
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, unique=True)
    added_at = Column(DateTime, default=func.now())
    __table_args__ = ( 
        Index("ix_asset_symbol_hash", 'symbol', postgresql_using='hash'),  
    )

class PairsMixin : 
    __abstract__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    pair_symbol = Column(String, nullable=False, unique=True)
    base_asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    quote_asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    base_asset_precision = Column(Integer)
    quote_asset_precision = Column(Integer)
    price = Column(Numeric(precision=38, scale=10))
    added_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now())

    tick_size = Column(Numeric(precision=38, scale=10))
    min_lot_size = Column(Numeric(precision=38, scale=10))
    max_lot_size =Column(Numeric(precision=38, scale=10))
    min_order_price = Column(Numeric(precision=38, scale=10))
    max_order_price = Column(Numeric(precision=38, scale=10))
    

class SpotPairs(Base, PairsMixin) : 
    __tablename__ = "spot_pairs" 
    __table_args__ = ( 
        Index("ix_spot_pair_symbol_hash", 'pair_symbol', postgresql_using='hash'), 
    )
    base_asset = relationship("Assets", foreign_keys=[PairsMixin.base_asset_id], back_populates="id")
    quote_asset = relationship("Assets", foreign_keys=[PairsMixin.quote_asset_id], back_populates="id")


class FuturesPairs(Base, PairsMixin) : 
    __tablename__ = "futures_pairs"
    __table_args__ = ( 
        Index("ix_futures_pair_symbol_hash", 'pair_symbol', postgresql_using='hash'), 
    )

    coin_m = Column(Boolean, nullable=False, default=False)
    mark_price = Column(Numeric(precision=38, scale=10))
    delivery_date = Column(DateTime)
    onboard_date = Column(DateTime)
    funding_rate = Column(Numeric(precision=38, scale=10))

    base_asset = relationship("Assets", foreign_keys=[PairsMixin.base_asset_id], back_populates="id")
    quote_asset = relationship("Assets", foreign_keys=[PairsMixin.quote_asset_id], back_populates="id")
    