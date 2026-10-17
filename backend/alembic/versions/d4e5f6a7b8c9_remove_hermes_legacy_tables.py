"""Altlasten aus Hermes entfernen (Issue #17): Chat, Familienmitglieder, Wartung, Pakete,
Finanzen und alte Web-Push-Abos (seit 46be834a94fe in push_devices übernommen).

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-14 17:30:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_TABLES = ("chat_messages", "family_members", "maintenance_tasks", "packages", "recurring_expenses", "push_subscriptions")


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in LEGACY_TABLES:
        if table in existing:
            op.drop_table(table)


def downgrade() -> None:
    # Bewusst ohne Wiederherstellung: Die Module gibt es nicht mehr. Daten liegen in den Backups.
    pass
