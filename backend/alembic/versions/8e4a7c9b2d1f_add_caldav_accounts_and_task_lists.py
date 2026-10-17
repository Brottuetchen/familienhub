"""add caldav_accounts and task_lists

Revision ID: 8e4a7c9b2d1f
Revises: 7d79098f55bd
Create Date: 2026-10-13 22:35:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8e4a7c9b2d1f'
down_revision: Union[str, None] = '7d79098f55bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bestandsschutz: Tabellen nur anlegen, wenn sie noch nicht existieren
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # CalDAV-Accounts pro Nutzer
    if 'caldav_accounts' not in existing_tables:
        op.create_table(
            'caldav_accounts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('url', sa.String(), nullable=False),
            sa.Column('username', sa.String(), nullable=False),
            sa.Column('password_enc', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_caldav_accounts_id'), 'caldav_accounts', ['id'], unique=False)
        op.create_index(op.f('ix_caldav_accounts_user_id'), 'caldav_accounts', ['user_id'], unique=True)

    # Task-Listen-Zuordnung
    if 'task_lists' not in existing_tables:
        op.create_table(
            'task_lists',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('caldav_url', sa.String(), nullable=False),
            sa.Column('display_name', sa.String(), nullable=False),
            sa.Column('kind', sa.String(), nullable=False),
            sa.Column('owner_user_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_caldav_url'), 'task_lists', ['caldav_url'], unique=True)
        op.create_index(op.f('ix_task_lists_id'), 'task_lists', ['id'], unique=False)
        op.create_index(op.f('ix_task_lists_user_id'), 'task_lists', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_task_lists_user_id'), table_name='task_lists')
    op.drop_index(op.f('ix_task_lists_id'), table_name='task_lists')
    op.drop_index(op.f('ix_caldav_url'), table_name='task_lists')
    op.drop_table('task_lists')

    op.drop_index(op.f('ix_caldav_accounts_user_id'), table_name='caldav_accounts')
    op.drop_index(op.f('ix_caldav_accounts_id'), table_name='caldav_accounts')
    op.drop_table('caldav_accounts')
