"""add notification_prefs and migrate webpush

Revision ID: 46be834a94fe
Revises: 8e4a7c9b2d1f
Create Date: 2026-10-14 00:09:50.957951
"""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa


revision: str = '46be834a94fe'
down_revision: Union[str, None] = '8e4a7c9b2d1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # notification_prefs-Tabelle anlegen
    if 'notification_prefs' not in existing_tables:
        op.create_table(
            'notification_prefs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('category', sa.String(), nullable=False),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('quiet_start', sa.Time(), nullable=True),
            sa.Column('quiet_end', sa.Time(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_notification_prefs_id'), 'notification_prefs', ['id'], unique=False)
        op.create_index(op.f('ix_notification_prefs_user_id'), 'notification_prefs', ['user_id'], unique=False)

    # Index-Umbenennung für task_lists (Alembic-Autogenerate)
    if 'task_lists' in existing_tables:
        # Prüfen, ob alter Index existiert
        indexes = inspector.get_indexes('task_lists')
        index_names = [idx['name'] for idx in indexes]

        with op.batch_alter_table('task_lists', schema=None) as batch_op:
            if 'ix_caldav_url' in index_names:
                batch_op.drop_index('ix_caldav_url')
            if 'ix_task_lists_caldav_url' not in index_names:
                batch_op.create_index(batch_op.f('ix_task_lists_caldav_url'), ['caldav_url'], unique=True)

    # Datenmigration: alte push_subscriptions nach push_devices übernehmen
    if 'push_subscriptions' in existing_tables and 'push_devices' in existing_tables:
        # Alte WebPush-Subscriptions migrieren
        result = conn.execute(sa.text(
            "SELECT id, endpoint, keys_json, user_id, user_agent, created_at FROM push_subscriptions"
        ))
        old_subs = result.fetchall()

        for sub in old_subs:
            # Subscription als JSON zusammenbauen
            try:
                keys = json.loads(sub.keys_json) if sub.keys_json else {}
            except (json.JSONDecodeError, TypeError):
                keys = {}

            subscription_json = json.dumps({
                "endpoint": sub.endpoint,
                "keys": keys
            })

            # Prüfen, ob bereits migriert (duplikate vermeiden)
            check = conn.execute(sa.text(
                "SELECT id FROM push_devices WHERE kind = 'webpush' AND token = :token"
            ), {"token": subscription_json})

            if not check.fetchone():
                # In push_devices einfügen
                conn.execute(sa.text(
                    """INSERT INTO push_devices (user_id, kind, token, device_name, last_seen, created_at)
                       VALUES (:user_id, 'webpush', :token, :device_name, :last_seen, :created_at)"""
                ), {
                    "user_id": sub.user_id or 0,
                    "token": subscription_json,
                    "device_name": sub.user_agent[:50] if sub.user_agent else "Browser",
                    "last_seen": sub.created_at,
                    "created_at": sub.created_at
                })

        # Hier kein eigenes Commit: Alembic schreibt die Transaktion selbst fest. Ein eigenes
        # Commit beendete auf Postgres die Alembic-Transaktion; alle weiteren Migrationen
        # und der Versionsstand gingen verloren.


def downgrade() -> None:
    # notification_prefs entfernen
    op.drop_index(op.f('ix_notification_prefs_user_id'), table_name='notification_prefs')
    op.drop_index(op.f('ix_notification_prefs_id'), table_name='notification_prefs')
    op.drop_table('notification_prefs')

    # Index zurück
    with op.batch_alter_table('task_lists', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_lists_caldav_url'))
        batch_op.create_index('ix_caldav_url', ['caldav_url'], unique=1)
