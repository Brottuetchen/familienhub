"""reminders: for_family (private vs. Familie)

Revision ID: b7c1d2e3f4a5
Revises: fa5e77df9c4d
Create Date: 2026-10-14 12:30:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c1d2e3f4a5"
down_revision: Union[str, None] = "fa5e77df9c4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = [c["name"] for c in sa.inspect(op.get_bind()).get_columns("reminders")]
    if "for_family" not in cols:
        with op.batch_alter_table("reminders") as batch:
            batch.add_column(sa.Column("for_family", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("reminders") as batch:
        batch.drop_column("for_family")
