"""Hub calendar: notes and recurrence

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-18 20:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("hub_events")}
    if "notes" not in cols:
        op.add_column("hub_events", sa.Column("notes", sa.Text(), nullable=True))
    if "recurrence" not in cols:
        op.add_column("hub_events", sa.Column("recurrence", sa.String(16), nullable=False, server_default="none"))


def downgrade() -> None:
    op.drop_column("hub_events", "recurrence")
    op.drop_column("hub_events", "notes")
