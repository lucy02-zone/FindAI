"""create lost items table

Revision ID: edbcd7d0b3df
Revises: 20261025_01
Create Date: 2026-10-28 11:35:57.937988

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'edbcd7d0b3df'
down_revision: Union[str, None] = '20261025_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lost_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("date_lost", sa.Date(), nullable=False),
        sa.Column("image_path", sa.String(length=512), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'open'"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_lost_items_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lost_items_status", "lost_items", ["status"])
    op.create_index("ix_lost_items_user_id", "lost_items", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_lost_items_user_id", table_name="lost_items")
    op.drop_index("ix_lost_items_status", table_name="lost_items")
    op.drop_table("lost_items")
