"""timetable: which plugin provides the lessons of a child, and the child's identifier in that plugin

Revision ID: c0b2e3f4a5c6
Revises: c0a1d2e3f4b5
Create Date: 2026-10-19 12:10:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c0b2e3f4a5c6"
down_revision: Union[str, None] = "c0a1d2e3f4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("timetable_sources"):  # old installation created by create_all
        return
    op.create_table(
        "timetable_sources",
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("plugin_id", sa.String(40), nullable=False),
        sa.Column("person_id", sa.String(200), nullable=False),
        sa.Column("person_name", sa.String(120), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("timetable_sources")
