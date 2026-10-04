"""Append-only issuer financial observations from SEC XBRL."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261004_0015"
down_revision = "20261004_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "financial_facts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("cik", sa.String(10), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("filed_on", sa.Date(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("cik", "fingerprint", name="uq_financial_fact"),
    )
    op.create_index("ix_financial_facts_cik", "financial_facts", ["cik"])
    op.create_index("ix_financial_facts_period_end", "financial_facts", ["period_end"])


def downgrade():
    op.drop_table("financial_facts")
