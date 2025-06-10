"""create enums

Revision ID: a7da70a70001
Revises: 7cff03da921f
Create Date: 2025-05-15 16:24:32.299409

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import os

# revision identifiers, used by Alembic.
revision: str = 'a7da70a70001'
down_revision: Union[str, None] = '7cff03da921f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_SCHEMA = "trading_app"
schema = os.environ.get("APP_SCHEMA", DEFAULT_SCHEMA)

ENUMS: dict[str, tuple[str, ...]] = {
    # models.trades.OrderSide
    "orderside": ("BUY", "SELL"),

    # models.OrderType
    "ordertype": (
        "LIMIT",
        "MARKET",
        "TAKE_PROFIT",
        "STOP",
        "STOP_MARKET",
        "TAKE_PROFIT_MARKET",
        "TRAILING_STOP_MARKET",
    ),

    # models.OrderTimeInForce
    "ordertimeinforce": ("GTC", "IOC", "FOK", "GTX", "GTD"),

    # models.OrderStatus
    "orderstatus": (
        "NEW",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCELED",
        "EXPIRED",
        "EXPIRED_IN_MATCH",
    ),

    # models.ExecutionType
    "executiontype": (
        "NEW",
        "CANCELED",
        "CALCULATED",
        "TRADE",
        "EXPIRED",
        "AMENDMENT",
    ),
}

def _create_enum(name: str, values: tuple[str, ...]) -> None:
    sa.Enum(*values, name=name, schema=schema).create(
        op.get_bind(), checkfirst=True
    )

def _drop_enum(name: str) -> None:
    sa.Enum(name=name, schema=schema).drop(
        op.get_bind(), checkfirst=True
    )

def upgrade() -> None:
    for name, values in ENUMS.items():
        _create_enum(name, values)

def downgrade() -> None:
    # drop in reverse order to satisfy dependencies
    for name in reversed(list(ENUMS.keys())):
        _drop_enum(name)
