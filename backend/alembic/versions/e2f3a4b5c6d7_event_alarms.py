"""Event reminders: hub event alarms, calendar-on-phone flag, sent log

Revision ID: e2f3a4b5c6d7
Revises: c0d1e2f3a4b5
Create Date: 2026-10-19 16:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "c0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "alarm_minutes" not in {c["name"] for c in inspector.get_columns("hub_events")}:
        op.add_column("hub_events", sa.Column("alarm_minutes", sa.Integer(), nullable=True))
    if "calendar_on_phone" not in {c["name"] for c in inspector.get_columns("users")}:
        op.add_column("users", sa.Column("calendar_on_phone", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "event_alarms_sent" not in inspector.get_table_names():
        op.create_table(
            "event_alarms_sent",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("key", sa.String(300), nullable=False),
            sa.Column("sent_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "key", name="uq_event_alarm_user_key"),
        )
        op.create_index("ix_event_alarms_sent_user_id", "event_alarms_sent", ["user_id"])
        op.create_index("ix_event_alarms_sent_sent_at", "event_alarms_sent", ["sent_at"])


def downgrade() -> None:
    op.drop_table("event_alarms_sent")
    op.drop_column("users", "calendar_on_phone")
    op.drop_column("hub_events", "alarm_minutes")
