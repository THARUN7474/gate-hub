"""v11: proposal source-content hash + benchmark_samples table.

1. classification_proposals.source_content_hash (nullable): SHA-256 of the exact
   question text+options the provider saw, so a later re-extraction/OCR fix is
   detectable as staleness instead of silently comparing an old opinion against
   changed input.
2. benchmark_samples: stratified sample selected for HUMAN gold review. Rows are
   created with status='pending_user_review'; the pipeline never assigns gold.
   Metrics read only 'gold_verified' rows.

Idempotent: on a fresh database create_all() already built both from the models.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = insp.get_table_names()
    if "classification_proposals" in tables:
        cols = {c["name"] for c in insp.get_columns("classification_proposals")}
        if "source_content_hash" not in cols:
            op.add_column("classification_proposals",
                          sa.Column("source_content_hash", sa.String(64), nullable=True))
    if "benchmark_samples" not in tables:
        op.create_table(
            "benchmark_samples",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("question_id", sa.String, sa.ForeignKey("questions.id"),
                      unique=True, index=True, nullable=False),
            sa.Column("batch", sa.String(40), index=True, nullable=False),
            sa.Column("stratum", sa.String(60), nullable=False),
            sa.Column("status", sa.String(20), nullable=False,
                      server_default="pending_user_review"),
            sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewer", sa.String(60), nullable=True),
            sa.Column("gold_section_id", sa.String(20), nullable=True),
            sa.Column("gold_primary_topic_id", sa.String(20), nullable=True),
            sa.Column("gold_concept_ids", sa.JSON, nullable=True),
            sa.Column("note", sa.Text, nullable=True),
        )


def downgrade() -> None:
    op.drop_table("benchmark_samples")
    op.drop_column("classification_proposals", "source_content_hash")
