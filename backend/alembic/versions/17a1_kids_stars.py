"""Kids mode: stars for tasks and rewards

Revision ID: 17a1c0de5701
Revises: a1b2c3d4e5f7
Create Date: 2026-10-19 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "17a1c0de5701"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "star_tasks" not in existing:
        op.create_table(
            "star_tasks",
            sa.Column("provider", sa.String(32), primary_key=True),
            sa.Column("task_uid", sa.String(255), primary_key=True),
            sa.Column("stars", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if "star_accounts" not in existing:
        op.create_table(
            "star_accounts",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("balance", sa.Integer(), nullable=False),
            sa.Column("reserved", sa.Integer(), nullable=False),
            sa.CheckConstraint("balance >= 0 AND reserved >= 0 AND reserved <= balance",
                               name="ck_star_account_not_negative"),
        )
    if "star_ledger" not in existing:
        op.create_table(
            "star_ledger",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("delta", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("ref", sa.String(300), nullable=False),
            sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("user_id", "kind", "ref", name="uq_star_ledger_ref"),
        )
        op.create_index("ix_star_ledger_user_id", "star_ledger", ["user_id"])
    if "star_rewards" not in existing:
        op.create_table(
            "star_rewards",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(120), nullable=False),
            sa.Column("price", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if "star_requests" not in existing:
        op.create_table(
            "star_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("reward_id", sa.Integer(), sa.ForeignKey("star_rewards.id", ondelete="SET NULL"), nullable=True),
            sa.Column("title", sa.String(120), nullable=False),
            sa.Column("price", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_star_requests_user_id", "star_requests", ["user_id"])


def downgrade() -> None:
    for table in ("star_requests", "star_rewards", "star_ledger", "star_accounts", "star_tasks"):
        op.drop_table(table)
