"""installed_plugins: plugins an admin installed from GitHub

Revision ID: d1e2f3a4b5c6
Revises: b9c0d1e2f3a4
Create Date: 2026-10-18 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("installed_plugins"):  # old installation created by create_all
        return
    op.create_table(
        "installed_plugins",
        sa.Column("id", sa.String(31), primary_key=True),
        sa.Column("repo_url", sa.String(300), nullable=False),
        sa.Column("sha", sa.String(40), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("manifest", sa.Text(), nullable=False),
        sa.Column("installed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("installed_at", sa.DateTime(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("installed_plugins")
