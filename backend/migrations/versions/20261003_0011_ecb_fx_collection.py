"""Persistent reference FX collection history and derivation evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261003_0011"
down_revision = "20261003_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "fx_rates", sa.Column("provider", sa.String(30), nullable=False, server_default="manual")
    )
    op.add_column("fx_rates", sa.Column("derivation", postgresql.JSONB()))
    op.create_table(
        "fx_collection_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_code", sa.String(50)),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("latest_reference_date", sa.Date()),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("preserved_manual_count", sa.Integer(), nullable=False),
        sa.Column("available_currencies", postgresql.JSONB()),
    )


def downgrade():
    op.drop_table("fx_collection_runs")
    op.drop_column("fx_rates", "derivation")
    op.drop_column("fx_rates", "provider")
