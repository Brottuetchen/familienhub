"""Recipe picture link (import from a link)

Revision ID: 16a1b2c3d4e5
Revises: 20a1b2c3d4e5
Create Date: 2026-10-19 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "16a1b2c3d4e5"
down_revision: Union[str, None] = "20a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = [c["name"] for c in sa.inspect(op.get_bind()).get_columns("recipes")]
    if "image_url" not in columns:
        op.add_column("recipes", sa.Column("image_url", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recipes") as batch:
        batch.drop_column("image_url")
