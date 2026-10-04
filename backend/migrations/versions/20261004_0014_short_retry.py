"""Shorten existing Alpha Vantage technical retry delays without resetting quota."""

from alembic import op

revision = "20261004_0014"
down_revision = "20261004_0013"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve request timestamps, status and consumed quota. Quota suspensions
    # and interrupted (unfinished) requests are not changed.
    op.execute("""
        UPDATE market_fetch_runs
        SET retry_at = LEAST(retry_at, finished_at + INTERVAL '5 minutes')
        WHERE provider = 'alpha_vantage'
          AND status = 'failed'
          AND finished_at IS NOT NULL
          AND retry_at IS NOT NULL
          AND error_code IS NOT NULL
          AND error_code NOT IN ('provider_quota', 'provider_rejected_or_quota')
    """)


def downgrade():
    # Historical operational deadlines cannot be reconstructed on downgrade.
    pass
