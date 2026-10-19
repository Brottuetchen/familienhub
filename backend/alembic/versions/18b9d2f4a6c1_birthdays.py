"""Birthdays, anniversaries and gift ideas

Revision ID: 18b9d2f4a6c1
Revises: a1b2c3d4e5f7
Create Date: 2026-10-19 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "18b9d2f4a6c1"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("birthdays"):
        op.create_table(
            "birthdays",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False, server_default="birthday"),
            sa.Column("month", sa.Integer(), nullable=False),
            sa.Column("day", sa.Integer(), nullable=False),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("remind_days_before", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_birthdays_user_id", "birthdays", ["user_id"])
    if not insp.has_table("gift_ideas"):
        op.create_table(
            "gift_ideas",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("birthday_id", sa.Integer(), sa.ForeignKey("birthdays.id", ondelete="CASCADE"), nullable=False),
            sa.Column("text", sa.String(300), nullable=False),
            sa.Column("link", sa.String(500), nullable=True),
            sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_gift_ideas_birthday_id", "gift_ideas", ["birthday_id"])


def downgrade() -> None:
    op.drop_index("ix_gift_ideas_birthday_id", table_name="gift_ideas")
    op.drop_table("gift_ideas")
    op.drop_index("ix_birthdays_user_id", table_name="birthdays")
    op.drop_table("birthdays")
