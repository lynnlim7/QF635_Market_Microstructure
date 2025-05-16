"""seed tables

Revision ID: 3167c552d4f4
Revises: c2c0eded93bb
Create Date: 2025-05-16 14:29:40.394998

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import os
import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from decimal import Decimal
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision: str = '3167c552d4f4'
down_revision: Union[str, None] = 'c2c0eded93bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_SCHEMA = "trading_app"
schema = os.environ.get("APP_SCHEMA", DEFAULT_SCHEMA)

metadata = sa.MetaData()

assets = sa.Table(
    "assets", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("symbol", sa.String, nullable=False),
    sa.Column("added_at", sa.DateTime, nullable=False, default=func.now()),
    schema=schema
)

spot_portfolio = sa.Table(
    "spot_portfolio", metadata,
    sa.Column("position_id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("asset_id", sa.String, nullable=False),
    sa.Column("amount", sa.Numeric(precision=38, scale=10), nullable=False),
    schema=schema
)

spot_pairs = sa.Table(
    "spot_pairs", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("base_asset_id", sa.Integer, sa.ForeignKey(f"{schema}.assets.id"), nullable=False),
    sa.Column("quote_asset_id", sa.Integer, sa.ForeignKey(f"{schema}.assets.id"), nullable=False),
    sa.Column("pair_symbol", sa.String, nullable=False),
    sa.Column("added_at", sa.DateTime, nullable=False, default=func.now()),
    sa.Column("base_asset_precision", sa.Integer),
    sa.Column("quote_asset_precision", sa.Integer),
    sa.Column("tick_size", sa.Numeric(precision=38, scale=10)),
    sa.Column("min_lot_size", sa.Numeric(precision=38, scale=10)),
    sa.Column("max_lot_size", sa.Numeric(precision=38, scale=10)),
    sa.Column("min_order_price", sa.Numeric(precision=38, scale=10)),
    sa.Column("max_order_price", sa.Numeric(precision=38, scale=10)),
    schema=schema
)

futures_pairs = sa.Table(
    "futures_pairs", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("base_asset_id", sa.Integer, sa.ForeignKey(f"{schema}.assets.id"), nullable=False),
    sa.Column("quote_asset_id", sa.Integer, sa.ForeignKey(f"{schema}.assets.id"), nullable=False),
    sa.Column("pair_symbol", sa.String, nullable=False),
    sa.Column("base_asset_precision", sa.Integer),
    sa.Column("quote_asset_precision", sa.Integer),
    sa.Column("added_at", sa.DateTime, nullable=False, default=func.now()),
    sa.Column("coin_m", sa.Boolean, default=False),
    sa.Column("delivery_date", sa.DateTime),
    sa.Column("onboard_date", sa.DateTime),
    sa.Column("tick_size", sa.Numeric(precision=38, scale=10)),
    sa.Column("min_lot_size", sa.Numeric(precision=38, scale=10)),
    sa.Column("max_lot_size", sa.Numeric(precision=38, scale=10)),
    sa.Column("min_order_price", sa.Numeric(precision=38, scale=10)),
    sa.Column("max_order_price", sa.Numeric(precision=38, scale=10)),
    schema=schema
)

futures_portfolio = sa.Table(
    "futures_portfolio", metadata,
    sa.Column("position_id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("pair_id", sa.String, nullable=False),
    sa.Column("amount", sa.Numeric(precision=38, scale=10), nullable=False),
    schema=schema
)


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    r = httpx.get("https://api.binance.com/api/v3/exchangeInfo")
    if r.status_code != 200 :
        raise(Exception("failed to retrieve exchange data"))

    data = r.json()
    asset_ids = {}

    symbols = set()
    spot_pairs_data = set()

    for symbol in data["symbols"] :
        symbols.add(symbol["baseAsset"])
        symbols.add(symbol["quoteAsset"])

        min_price, max_price, min_lot_size, max_lot_size, tick_size = None, None, None, None, None
        for f in symbol["filters"] : 
            if f["filterType"] == "PRICE_FILTER" : 
                min_price = f.get("minPrice")
                if min_price : 
                    min_price = Decimal(min_price)
                max_price = f.get("maxPrice")
                if max_price : 
                    max_price = Decimal(max_price)
            if f["filterType"] == "LOT_SIZE" : 
                min_lot_size = f.get("minQty")
                if min_lot_size : 
                    min_lot_size = Decimal(min_lot_size)
                tick_size = f.get("stepSize")
                if tick_size : 
                    tick_size = Decimal(tick_size)
                max_lot_size = f.get("maxQty")
                if max_lot_size : 
                    max_lot_size = Decimal(max_lot_size)

        spot_pairs_data.add((
            symbol["symbol"], 
            symbol["baseAsset"], 
            symbol["quoteAsset"], 
            symbol["baseAssetPrecision"], 
            symbol["quoteAssetPrecision"],
            tick_size,
            min_lot_size,
            max_lot_size, 
            min_price,
            max_price
        ))

    for asset in symbols : 
        stmt = insert(assets).values(symbol=asset).on_conflict_do_nothing(index_elements=['symbol']).returning(assets.c.id)
        result = bind.execute(stmt)
        asset_ids[asset] = result.scalar_one()
        stmt = insert(spot_portfolio).values(asset_id=asset_ids[asset], amount=0.0)
        bind.execute(stmt)

    for pair in spot_pairs_data :
        stmt = insert(spot_pairs).values(
            pair_symbol = pair[0],
            base_asset_id = asset_ids[pair[1]],
            quote_asset_id = asset_ids[pair[2]],
            base_asset_precision = pair[3],
            quote_asset_precision = pair[4],
            tick_size = pair[5],
            min_lot_size = pair[6],
            max_lot_size = pair[7],
            min_order_price = pair[8],
            max_order_price = pair[9]
        )
        bind.execute(stmt)

    r = httpx.get("https://testnet.binancefuture.com/fapi/v1/exchangeInfo")
    if r.status_code != 200 :
        raise(Exception("failed to retrieve exchange data"))

    data = r.json()

    ftr_pairs_data = set()
    ftr_pair_ids = {}

    for symbol in data["symbols"] : 
        if symbol["contractType"] != "PERPETUAL" or symbol["status"] == "BREAK" : 
            continue
        min_price, max_price, min_lot_size, max_lot_size, tick_size = None, None, None, None, None
        for f in symbol["filters"] : 
            if f["filterType"] == "PRICE_FILTER" : 
                min_price = f.get("minPrice")
                if min_price : 
                    min_price = Decimal(min_price)
                max_price = f.get("maxPrice")
                if max_price : 
                    max_price = Decimal(max_price)
            if f["filterType"] == "LOT_SIZE" : 
                min_lot_size = f.get("minQty")
                if min_lot_size : 
                    min_lot_size = Decimal(min_lot_size)
                tick_size = f.get("stepSize")
                if tick_size : 
                    tick_size = Decimal(tick_size)
                max_lot_size = f.get("maxQty")
                if max_lot_size : 
                    max_lot_size = Decimal(max_lot_size)

        ftr_pairs_data.add((
            symbol["symbol"], 
            symbol["baseAsset"], 
            symbol["quoteAsset"], 
            symbol["baseAssetPrecision"], 
            symbol["quotePrecision"],
            symbol["deliveryDate"],
            symbol["onboardDate"],
            tick_size,
            min_lot_size,
            max_lot_size, 
            min_price,
            max_price
        ))

    for pair in ftr_pairs_data :

        # Skip random unlisted coins
        if pair[1] not in asset_ids : 
            continue
        
        stmt = insert(futures_pairs).values(
            pair_symbol = pair[0],
            base_asset_id = asset_ids[pair[1]],
            quote_asset_id = asset_ids[pair[2]],
            base_asset_precision = pair[3],
            quote_asset_precision = pair[4],
            delivery_date = datetime.fromtimestamp(pair[5]/1000, timezone.utc),
            onboard_date = datetime.fromtimestamp(pair[6]/1000, timezone.utc),
            tick_size = pair[7],
            min_lot_size = pair[8],
            max_lot_size = pair[9],
            min_order_price = pair[10],
            max_order_price = pair[11]
        ).returning(futures_pairs.c.id)
        result = bind.execute(stmt)
        ftr_pair_ids[pair[0]] = result.scalar_one()

    for _, v in ftr_pair_ids.items() :
        stmt = insert(futures_portfolio).values({
            "pair_id" : v,
            "amount" : 0.0
        })
        bind.execute(stmt)
    session.commit()

def downgrade() -> None:
    """Downgrade schema."""
    pass