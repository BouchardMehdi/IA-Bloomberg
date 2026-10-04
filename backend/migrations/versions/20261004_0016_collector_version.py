"""Remember collection coverage versions without changing prior observations."""

import sqlalchemy as sa
from alembic import op

revision = "20261004_0016"
down_revision = "20261004_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("collection_runs", sa.Column("collector_version", sa.String(32), nullable=True))


def downgrade():
    op.drop_column("collection_runs", "collector_version")
