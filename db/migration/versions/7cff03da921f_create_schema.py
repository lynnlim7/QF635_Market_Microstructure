"""create schema

Revision ID: 7cff03da921f
Revises: 
Create Date: 2025-05-15 16:23:38.211495

"""
import os
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7cff03da921f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_SCHEMA = "trading_app"
schema = os.environ.get("APP_SCHEMA", DEFAULT_SCHEMA)

def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")


def downgrade() -> None:
    op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")