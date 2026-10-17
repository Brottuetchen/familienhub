"""reminders.fire_on: Erinnerung beim Heimkommen (#26)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-14 20:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("reminders")}
    if "fire_on" not in columns:
        op.add_column("reminders", sa.Column("fire_on", sa.String(), nullable=False, server_default="time"))


def downgrade() -> None:
    op.drop_column("reminders", "fire_on")
