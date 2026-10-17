"""Native persönliche Habitica-Providerdaten (#47)."""
from alembic import op
import sqlalchemy as sa

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    tables = {
        "habitica_accounts": (
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
            sa.Column("server_url", sa.String(), nullable=False),
            sa.Column("remote_user_id", sa.String(), nullable=False),
            sa.Column("api_key_enc", sa.Text(), nullable=False),
            sa.Column("pending_operation", sa.String(), nullable=True),
            sa.UniqueConstraint("server_url", "remote_user_id")),
        "habitica_selections": (
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
            sa.Column("account_ref", sa.String(), primary_key=True),
            sa.Column("remote_id", sa.String(), primary_key=True)),
        "habitica_operations": (
            sa.Column("key", sa.String(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("account_ref", sa.String(), nullable=False),
            sa.Column("fingerprint", sa.String(), nullable=False),
            sa.Column("state", sa.String(), nullable=False),
            sa.Column("result", sa.JSON(), nullable=True)),
    }
    for name, columns in tables.items():
        if not sa.inspect(op.get_bind()).has_table(name):
            op.create_table(name, *columns)


def downgrade():
    for name in ("habitica_operations", "habitica_selections", "habitica_accounts"):
        op.drop_table(name)
