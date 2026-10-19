"""plugin and theme store: extra sources, and where an installed plugin or theme came from

Revision ID: f8a9b0c1d2e3
Revises: e2f3a4b5c6d7
Create Date: 2026-10-19 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("store_sources"):  # old installation created by create_all
        op.create_table(
            "store_sources",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("repo_url", sa.String(300), nullable=False, unique=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("added_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("added_at", sa.DateTime(), nullable=False),
        )
    if "store_source" not in _columns("installed_plugins"):
        op.add_column("installed_plugins", sa.Column("store_source", sa.String(32), nullable=True))
    theme_cols = _columns("themes")
    for name, size in (("store_id", 64), ("store_source", 32), ("store_sha", 40), ("store_version", 32)):
        if name not in theme_cols:
            op.add_column("themes", sa.Column(name, sa.String(size), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("themes") as batch:
        for name in ("store_version", "store_sha", "store_source", "store_id"):
            batch.drop_column(name)
    with op.batch_alter_table("installed_plugins") as batch:
        batch.drop_column("store_source")
    op.drop_table("store_sources")
