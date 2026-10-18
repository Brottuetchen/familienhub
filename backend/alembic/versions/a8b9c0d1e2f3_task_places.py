"""Tasks by recipient: preferred task place per user, assignment records

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-10-19 09:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "task_place" not in {c["name"] for c in inspector.get_columns("users")}:
        op.add_column("users", sa.Column("task_place", sa.String(32), nullable=True))
    if "task_assignments" not in inspector.get_table_names():
        op.create_table(
            "task_assignments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("creator_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(32), nullable=False),
            sa.Column("account_ref", sa.String(100), nullable=False, server_default=""),
            sa.Column("remote_uid", sa.String(200), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("due", sa.String(32), nullable=True),
            sa.Column("fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sync_ok", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("synced_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_task_assignments_creator_id", "task_assignments", ["creator_id"])
        op.create_index("ix_task_assignments_assignee_id", "task_assignments", ["assignee_id"])


def downgrade() -> None:
    op.drop_table("task_assignments")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("task_place")
