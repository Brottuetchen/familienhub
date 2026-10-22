"""Named shopping and task lists, plus per-item assignment.

Revision ID: f1e2d3c4b5a6
Revises: c0b2e3f4a5c6
Create Date: 2026-10-23 01:10:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1e2d3c4b5a6"
down_revision: Union[str, None] = "c0b2e3f4a5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(insp, table: str) -> set:
    return {c["name"] for c in insp.get_columns(table)} if insp.has_table(table) else set()


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("named_lists"):
        op.create_table(
            "named_lists",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    insp = sa.inspect(op.get_bind())
    if insp.has_table("hub_shopping_items"):
        have = _cols(insp, "hub_shopping_items")
        if "list_id" not in have:
            op.add_column("hub_shopping_items", sa.Column("list_id", sa.Integer(), nullable=True))
        if "assignee_id" not in have:
            op.add_column("hub_shopping_items", sa.Column("assignee_id", sa.Integer(), nullable=True))
    if insp.has_table("hub_tasks") and "list_id" not in _cols(insp, "hub_tasks"):
        op.add_column("hub_tasks", sa.Column("list_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("hub_tasks") and "list_id" in _cols(insp, "hub_tasks"):
        op.drop_column("hub_tasks", "list_id")
    if insp.has_table("hub_shopping_items"):
        have = _cols(insp, "hub_shopping_items")
        if "assignee_id" in have:
            op.drop_column("hub_shopping_items", "assignee_id")
        if "list_id" in have:
            op.drop_column("hub_shopping_items", "list_id")
    if insp.has_table("named_lists"):
        op.drop_table("named_lists")
