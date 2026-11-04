"""v11 fix: frozen pre-review baseline on benchmark_samples.

Evaluation must compare the machine prediction FROZEN at sampling time (or an
independent provider's proposals) against human gold - never the live
classifications row, which after a human correction IS the gold. These nullable
columns snapshot the prediction and the input hash at sample creation.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

COLS = [
    ("baseline_section_id", sa.String(20)),
    ("baseline_primary_topic_id", sa.String(20)),
    ("baseline_concept_ids", sa.JSON),
    ("baseline_confidence", sa.Float),
    ("baseline_run_id", sa.Integer),
    ("baseline_content_hash", sa.String(64)),
]


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "benchmark_samples" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("benchmark_samples")}
    for name, typ in COLS:
        if name not in have:
            op.add_column("benchmark_samples", sa.Column(name, typ, nullable=True))


def downgrade() -> None:
    for name, _ in COLS:
        op.drop_column("benchmark_samples", name)
