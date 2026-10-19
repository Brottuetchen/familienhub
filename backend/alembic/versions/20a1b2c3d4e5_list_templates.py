"""Reusable template lists

Revision ID: 20a1b2c3d4e5
Revises: a1b2c3d4e5f7
Create Date: 2026-10-19 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20a1b2c3d4e5"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "list_templates" not in tables:
        op.create_table(
            "list_templates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "list_template_items" not in tables:
        op.create_table(
            "list_template_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("template_id", sa.Integer(), sa.ForeignKey("list_templates.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("note", sa.String(200), nullable=False),
        )
        op.create_index("ix_list_template_items_template_id", "list_template_items", ["template_id"])


def downgrade() -> None:
    op.drop_table("list_template_items")
    op.drop_table("list_templates")
