"""notification_log (Verlauf) und service_keys (Benachrichtigungs-Eingang)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-14 18:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "notification_log" not in existing:
        op.create_table(
            "notification_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("category", sa.String(), nullable=False),
            sa.Column("route", sa.String(), nullable=True),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("delivered", sa.Integer(), nullable=False),
            sa.Column("suppressed", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("read_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_notification_log_id", "notification_log", ["id"])
        op.create_index("ix_notification_log_user_id", "notification_log", ["user_id"])
        op.create_index("ix_notification_log_created_at", "notification_log", ["created_at"])
    if "service_keys" not in existing:
        op.create_table(
            "service_keys",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("key_hash", sa.String(), nullable=False),
            sa.Column("hint", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_service_keys_id", "service_keys", ["id"])
        op.create_index("ix_service_keys_key_hash", "service_keys", ["key_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("service_keys")
    op.drop_table("notification_log")
