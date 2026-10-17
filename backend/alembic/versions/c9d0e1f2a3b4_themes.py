"""themes: von Admins installierte Farbschemata

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-17 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("themes"):  # Alt-Installation per create_all
        return
    op.create_table(
        "themes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False, unique=True),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("themes")
