"""Scopes for personal API tokens (voice assistants)

Revision ID: 21a0b1c2d3e4
Revises: 19a0b1c2d3e4
Create Date: 2026-10-19 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "21a0b1c2d3e4"
down_revision: Union[str, None] = "19a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("api_tokens")}
    if "scopes" not in cols:
        # NULL = unrestricted (tokens created before scopes existed); otherwise space-separated scope names
        op.add_column("api_tokens", sa.Column("scopes", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("api_tokens") as batch:
        batch.drop_column("scopes")
