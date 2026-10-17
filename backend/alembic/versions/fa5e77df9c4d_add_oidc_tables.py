"""add oidc tables

Revision ID: fa5e77df9c4d
Revises: 46be834a94fe
Create Date: 2026-10-14 00:36:42.547354
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'fa5e77df9c4d'
down_revision: Union[str, None] = '46be834a94fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # OIDC-Session-Daten (state, nonce, code_verifier)
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table('oidc_sessions'):
        op.create_table(
            'oidc_sessions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('state', sa.String(), nullable=False),
            sa.Column('nonce', sa.String(), nullable=False),
            sa.Column('code_verifier', sa.String(), nullable=False),
            sa.Column('client_type', sa.String(), nullable=False),  # 'web' oder 'app'
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('state')
        )
        op.create_index(op.f('ix_oidc_sessions_state'), 'oidc_sessions', ['state'], unique=True)

    # App-Exchange-Codes (einmalig verwendbar, 60s gültig)
    if not inspector.has_table('oidc_exchange_codes'):
        op.create_table(
            'oidc_exchange_codes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('code', sa.String(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('used', sa.Boolean(), default=False, nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code')
        )
        op.create_index(op.f('ix_oidc_exchange_codes_code'), 'oidc_exchange_codes', ['code'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_oidc_exchange_codes_code'), table_name='oidc_exchange_codes')
    op.drop_table('oidc_exchange_codes')
    op.drop_index(op.f('ix_oidc_sessions_state'), table_name='oidc_sessions')
    op.drop_table('oidc_sessions')

