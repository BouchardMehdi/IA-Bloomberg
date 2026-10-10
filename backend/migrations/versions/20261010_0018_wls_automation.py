"""Sourced WLS identity observations and explicit provisional simulation policy."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261010_0018"
down_revision = "20261004_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wls_identity_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("bloomberg_identifier", sa.String(100), nullable=False),
        sa.Column("query_key", sa.String(100), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("query", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("data", postgresql.JSONB()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wls_identity_lookup",
        "wls_identity_observations",
        ["source_hash", "bloomberg_identifier"],
    )
    op.add_column(
        "paper_portfolios",
        sa.Column("wls_policy", sa.String(30), nullable=False, server_default="verified"),
    )
    op.add_column("paper_trades", sa.Column("universe_evidence", postgresql.JSONB()))


def downgrade():
    op.drop_column("paper_trades", "universe_evidence")
    op.drop_column("paper_portfolios", "wls_policy")
    op.drop_table("wls_identity_observations")
