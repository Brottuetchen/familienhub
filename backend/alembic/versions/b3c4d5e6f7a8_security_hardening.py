"""Sicherheit: Refresh-Tokens gehasht, PKCE-Bindung des OIDC-Rücksprungs

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-10-18 03:30:00
"""
import hashlib
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in ("oidc_sessions", "oidc_exchange_codes"):
        if insp.has_table(table) and "app_challenge" not in {c["name"] for c in insp.get_columns(table)}:
            op.add_column(table, sa.Column("app_challenge", sa.String(), nullable=True))
    if insp.has_table("refresh_tokens"):
        # Bestehende Sitzungen bleiben gültig: Klartext-Tokens werden in ihren SHA-256 umgewandelt
        rows = bind.execute(sa.text("SELECT id, token FROM refresh_tokens")).fetchall()
        for row_id, token in rows:
            if token and not _HEX64.match(token):
                bind.execute(sa.text("UPDATE refresh_tokens SET token = :t WHERE id = :i"),
                             {"t": hashlib.sha256(token.encode()).hexdigest(), "i": row_id})


def downgrade() -> None:
    # Hashes lassen sich nicht zurückrechnen: nach einem Downgrade müssen sich alle neu anmelden.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("refresh_tokens"):
        bind.execute(sa.text("UPDATE refresh_tokens SET revoked = :r"), {"r": True})
    for table in ("oidc_exchange_codes", "oidc_sessions"):
        if insp.has_table(table):
            op.drop_column(table, "app_challenge")
