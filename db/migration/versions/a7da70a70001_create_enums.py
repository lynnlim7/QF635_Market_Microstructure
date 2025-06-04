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

def upgrade() -> None:
    order_side = sa.Enum('BUY', 'SELL', name='orderside', schema=schema)
    order_side.create(op.get_bind(), checkfirst=True)

    order_type = sa.Enum(
        'LIMIT', 'MARKET', 'STOP_LOSS', 'STOP_LIMIT',
        'TAKE_PROFIT', 'TAKE_PROFIT_LIMIT', 'LIMIT_MAKER', 'OCO',
        name='ordertype',
        schema=schema
    )
    order_type.create(op.get_bind(), checkfirst=True)

    order_time_in_force = sa.Enum('GTC', 'IOC', 'FOK', name='ordertimeinforce', schema=schema)
    order_time_in_force.create(op.get_bind(), checkfirst=True)

    order_status = sa.Enum("open", "pending", "partially_filled", 
                           "filled", "rejected", "expired", 
                           name="orderstatus", schema=schema)
    order_status.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    order_type = sa.Enum(name='ordertype', schema=schema)
    order_type.drop(op.get_bind(), checkfirst=True)

    order_side = sa.Enum(name='orderside', schema=schema)
    order_side.drop(op.get_bind(), checkfirst=True)

    order_time_in_force = sa.Enum(name='ordertimeinforce', schema=schema)
    order_time_in_force.drop(op.get_bind(), checkfirst=True)

    order_status = sa.Enum(name='orderstatus', schema=schema)
    order_status.drop(op.get_bind(), checkfirst=True)
