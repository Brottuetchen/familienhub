"""Timetable of children

Revision ID: 19a0b1c2d3e4
Revises: 18b9d2f4a6c1
Create Date: 2026-10-19 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "19a0b1c2d3e4"
down_revision: Union[str, None] = "18b9d2f4a6c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "timetable_entries" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "timetable_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("week", sa.String(length=3), nullable=False),
        sa.Column("start", sa.String(length=5), nullable=False),
        sa.Column("end", sa.String(length=5), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("location", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_timetable_entries_id", "timetable_entries", ["id"])
    op.create_index("ix_timetable_entries_child_id", "timetable_entries", ["child_id"])


def downgrade() -> None:
    op.drop_table("timetable_entries")
