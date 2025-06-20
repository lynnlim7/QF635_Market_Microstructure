"""migrate_tables


Revision ID: 94114ecee8a3
Revises: a7da70a70001
Create Date: 2025-05-30 16:59:35.239608

"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '94114ecee8a3'
down_revision: Union[str, None] = 'a7da70a70001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_SCHEMA = "trading_app"
schema = os.environ.get("APP_SCHEMA", DEFAULT_SCHEMA)

def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "futures_order",
        sa.Column("order_id", sa.BigInteger(), primary_key=True),
        sa.Column("client_order_id", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),

        sa.Column("side", postgresql.ENUM("BUY", "SELL", name="orderside", schema=schema, native_enum=True, create_type=False), nullable=False),
        sa.Column("position_side", sa.String(8), nullable=False),
        sa.Column("exec_type", postgresql.ENUM("NEW", "CANCELLED", "CALCULATED", "TRADE", "EXPIRED", "AMENDMENT", name="executiontype", schema=schema, native_enum=True, create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM("NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", name="orderstatus", schema=schema, native_enum=True, create_type=False), nullable=False),
        sa.Column("order_type", postgresql.ENUM("LIMIT", "MARKET", "TAKE_PROFIT", "STOP", "STOP_MARKET", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET", name="ordertype", schema=schema, native_enum=True, create_type=False), nullable=False),
        sa.Column("time_in_force", postgresql.ENUM("GTC", "IOC", "FOK", "GTX", "GTD", name="ordertimeinforce", schema=schema, native_enum=True, create_type=False), nullable=True),

        sa.Column("orig_qty", sa.Numeric(38, 10), nullable=False),
        sa.Column("cum_filled_qty", sa.Numeric(38, 10), nullable=False),
        sa.Column("avg_price", sa.Numeric(38, 10)),
        sa.Column("last_qty", sa.Numeric(38, 10), nullable=False),
        sa.Column("last_price", sa.Numeric(38, 10)),
        sa.Column("commission", sa.Numeric(38, 10), nullable=False, server_default="0"),
        sa.Column("commission_asset", sa.String(12)),
        sa.Column("realized_pnl", sa.Numeric(38, 10), nullable=False, server_default="0"),

        sa.Column("stop_price", sa.Numeric(38, 10)),
        sa.Column("activation_price", sa.Numeric(38, 10)),
        sa.Column("callback_rate", sa.Numeric(38, 10)),

        sa.Column("is_maker", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("event_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("trade_time_ms", sa.BigInteger(), nullable=False),

        sa.PrimaryKeyConstraint('order_id'),
        schema=schema,
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('futures_order', schema='trading_app')
    # ### end Alembic commands ###
