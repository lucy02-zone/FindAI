"""create lost items table

Revision ID: 82bf2b8f39bf
Revises: edbcd7d0b3df
Create Date: 2026-10-28 11:42:45.693404

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '82bf2b8f39bf'
down_revision: Union[str, None] = 'edbcd7d0b3df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
