"""User language for push texts (#24)

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-10-18 23:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "language" not in {c["name"] for c in inspector.get_columns("users")}:
        op.add_column("users", sa.Column("language", sa.String(5), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "language")
