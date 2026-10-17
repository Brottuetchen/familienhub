"""paperless_accounts: persönlicher Paperless-Zugang (#30)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-17 17:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("paperless_accounts"):
        return
    op.create_table(
        "paperless_accounts",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("token_enc", sa.Text(), nullable=False),
        sa.Column("remote_username", sa.String(150), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("paperless_accounts")
