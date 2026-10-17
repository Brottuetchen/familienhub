"""Profil: Anzeigename, Avatar-Farbe, Profilbild

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-17 16:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    columns = {c["name"] for c in insp.get_columns("users")}
    if "display_name" not in columns:
        op.add_column("users", sa.Column("display_name", sa.String(40), nullable=True))
    if "avatar_color" not in columns:
        op.add_column("users", sa.Column("avatar_color", sa.String(7), nullable=True))
    if "has_avatar" not in columns:
        op.add_column("users", sa.Column("has_avatar", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "avatar_version" not in columns:
        op.add_column("users", sa.Column("avatar_version", sa.Integer(), nullable=False, server_default="0"))
    if not insp.has_table("user_avatars"):
        op.create_table(
            "user_avatars",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("content", sa.LargeBinary(), nullable=False),
            sa.Column("mime", sa.String(20), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("user_avatars")
    for col in ("avatar_version", "has_avatar", "avatar_color", "display_name"):
        op.drop_column("users", col)
