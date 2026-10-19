"""meal plan: recipes of external plugins (plugin id, the plugin's recipe id, display data)

Revision ID: c0a1d2e3f4b5
Revises: f8a9b0c1d2e3
Create Date: 2026-10-19 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c0a1d2e3f4b5"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("meal_plan")}
    if "source" not in cols:
        op.add_column("meal_plan", sa.Column("source", sa.String(40), nullable=True))
        op.create_index("ix_meal_plan_source", "meal_plan", ["source"])
    if "external_id" not in cols:
        op.add_column("meal_plan", sa.Column("external_id", sa.String(200), nullable=True))
    if "meta" not in cols:
        op.add_column("meal_plan", sa.Column("meta", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("meal_plan") as batch:
        batch.drop_index("ix_meal_plan_source")
        batch.drop_column("meta")
        batch.drop_column("external_id")
        batch.drop_column("source")
