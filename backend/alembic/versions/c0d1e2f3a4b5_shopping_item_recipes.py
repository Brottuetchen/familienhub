"""Recipes per shopping entry (#69)

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-10-19 09:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "shopping_item_recipes" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "shopping_item_recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("item_key", sa.String(220), nullable=False),
        sa.Column("recipes", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("scope", "item_key", name="uq_shopping_item_recipes"),
    )


def downgrade() -> None:
    op.drop_table("shopping_item_recipes")
