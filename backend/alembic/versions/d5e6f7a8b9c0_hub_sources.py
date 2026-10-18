"""Built-in sources: hub tasks, shopping list, family calendar

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-18 14:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("hub_tasks"):
        op.create_table(
            "hub_tasks",
            sa.Column("uid", sa.String(64), primary_key=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("due", sa.String(32), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=True),
            sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("family", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("recurrence", sa.String(16), nullable=False, server_default="none"),
            sa.Column("rotation", sa.JSON(), nullable=False),
            sa.Column("successor_uid", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_hub_tasks_created_by", "hub_tasks", ["created_by"])
        op.create_index("ix_hub_tasks_assignee_id", "hub_tasks", ["assignee_id"])
    if not insp.has_table("hub_shopping_items"):
        op.create_table(
            "hub_shopping_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("summary", sa.String(200), nullable=False),
            sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
    if not insp.has_table("hub_events"):
        op.create_table(
            "hub_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("start", sa.DateTime(), nullable=False),
            sa.Column("end", sa.DateTime(), nullable=False),
            sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("location", sa.String(200), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_hub_events_start", "hub_events", ["start"])


def downgrade() -> None:
    op.drop_table("hub_events")
    op.drop_table("hub_shopping_items")
    op.drop_table("hub_tasks")
