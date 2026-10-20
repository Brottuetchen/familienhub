"""reward actions: an optional plugin action per reward (kids mode)

Revision ID: b0a1c2d3e4f5
Revises: f8a9b0c1d2e3
Create Date: 2026-10-19 14:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b0a1c2d3e4f5"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (("action_plugin", sa.String(32)), ("action_id", sa.String(64)), ("action_params", sa.Text()))


def _columns() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("star_rewards")}


def upgrade() -> None:
    have = _columns()  # an installation created by create_all may already have them
    for name, kind in COLUMNS:
        if name not in have:
            op.add_column("star_rewards", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("star_rewards") as batch:
        for name, _ in reversed(COLUMNS):
            batch.drop_column(name)
