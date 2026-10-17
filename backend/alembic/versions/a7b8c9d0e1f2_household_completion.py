"""Abschlussbelege für idempotente Haushaltsrotation.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    if not sa.inspect(op.get_bind()).has_table("task_completions"):
        op.create_table("task_completions",
                        sa.Column("uid", sa.String(), nullable=False),
                        sa.PrimaryKeyConstraint("uid"))


def downgrade():
    op.drop_table("task_completions")
