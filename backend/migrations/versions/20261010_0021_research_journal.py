"""Authored research decisions and immutable revisions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261010_0021"
down_revision = "20261010_0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("research_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("instrument_id", sa.Uuid(), sa.ForeignKey("market_instruments.id"), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), sa.ForeignKey("paper_portfolios.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_research_decisions_instrument_id", "research_decisions", ["instrument_id"])
    op.create_table("decision_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("decision_id", sa.Uuid(), sa.ForeignKey("research_decisions.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("client_request_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("author", sa.String(80), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", JSONB(), nullable=False),
        sa.UniqueConstraint("decision_id", "version"))
    op.create_index("ix_decision_revisions_decision_id", "decision_revisions", ["decision_id"])


def downgrade():
    op.drop_table("decision_revisions")
    op.drop_table("research_decisions")
