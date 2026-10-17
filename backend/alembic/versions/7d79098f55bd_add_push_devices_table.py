"""add push_devices table

Revision ID: 7d79098f55bd
Revises: 5a8ce1fa5469
Create Date: 2026-10-13 22:13:34.898819
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7d79098f55bd'
down_revision: Union[str, None] = '5a8ce1fa5469'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tabelle nur anlegen, wenn sie noch nicht existiert (Bestandsschutz)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'push_devices' not in inspector.get_table_names():
        op.create_table(
            'push_devices',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('kind', sa.String(), nullable=False),
            sa.Column('token', sa.Text(), nullable=False),
            sa.Column('device_name', sa.String(), nullable=True),
            sa.Column('last_seen', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_push_devices_id'), 'push_devices', ['id'], unique=False)
        op.create_index(op.f('ix_push_devices_user_id'), 'push_devices', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_push_devices_user_id'), table_name='push_devices')
    op.drop_index(op.f('ix_push_devices_id'), table_name='push_devices')
    op.drop_table('push_devices')
