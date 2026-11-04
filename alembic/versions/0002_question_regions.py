"""question regions: store source-PDF region references, stop storing crops

Idempotent: migration 0001 builds the schema with Base.metadata.create_all(),
i.e. from the CURRENT models, so on a fresh database this column already
exists by the time 0002 runs. We only add it when it is genuinely missing
(databases that were created at the 0001 revision long ago).

Revision ID: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}

def upgrade() -> None:
    if not _has_column("questions", "regions_json"):
        op.add_column("questions", sa.Column("regions_json", sa.Text(), nullable=True))

def downgrade() -> None:
    if _has_column("questions", "regions_json"):
        op.drop_column("questions", "regions_json")
