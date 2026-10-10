"""Shared workspace, alerts and sourced research additions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261010_0020"
down_revision = "20261010_0019"
branch_labels = None
depends_on = None

TABLES = ("workspace_users", "workspace_sessions", "workspace_alerts", "alert_receipts",
          "workspace_cursors", "instrument_profiles", "benchmark_points", "data_proposals")


def identifier():
    return sa.Column("id", sa.Uuid(), primary_key=True)


def instrument(nullable=False):
    return sa.Column("instrument_id", sa.Uuid(), sa.ForeignKey("market_instruments.id"), nullable=nullable)


def observed():
    return sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False)


def data():
    return sa.Column("data", JSONB(), nullable=False)


def upgrade():
    op.create_table("workspace_users", identifier(),
        sa.Column("username", sa.String(80), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(12), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False))
    op.create_table("workspace_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("workspace_users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_workspace_sessions_expires_at", "workspace_sessions", ["expires_at"])
    op.create_table("workspace_alerts", identifier(),
        sa.Column("dedup_key", sa.String(255), unique=True, nullable=False),
        sa.Column("kind", sa.String(30), nullable=False), instrument(True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), data())
    op.create_index("ix_workspace_alerts_kind", "workspace_alerts", ["kind"])
    op.create_index("ix_workspace_alerts_created_at", "workspace_alerts", ["created_at"])
    op.create_table("alert_receipts", sa.Column("reader", sa.String(80), primary_key=True),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("workspace_alerts.id"), primary_key=True))
    op.create_table("workspace_cursors", sa.Column("name", sa.String(40), primary_key=True), data())
    op.create_table("instrument_profiles", identifier(), instrument(),
        sa.Column("fingerprint", sa.String(64), nullable=False), observed(), data(),
        sa.UniqueConstraint("instrument_id", "fingerprint"))
    op.create_table("benchmark_points", identifier(),
        sa.Column("series", sa.String(100), nullable=False),
        sa.Column("session_date", sa.String(10), nullable=False), data(), sa.UniqueConstraint("series", "session_date"))
    op.create_table("data_proposals", identifier(), instrument(),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True), observed(), data())


def downgrade():
    for name in reversed(TABLES):
        op.drop_table(name)
