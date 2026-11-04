"""classification_proposals table (v10)

Independent per-provider proposals: an API run's second opinion, stored
separately so it never overwrites the classifications table (agent/manual
labels, human corrections, verified rows). One row per
(question, provider, model, prompt_version).

Idempotent: on a fresh database create_all() already built this table from
the current models.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "classification_proposals" in insp.get_table_names():
        return
    op.create_table(
        "classification_proposals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("question_id", sa.String, sa.ForeignKey("questions.id"), index=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("classification_runs.id"), nullable=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(300), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("taxonomy_version", sa.String(30), nullable=False),
        sa.Column("section_id", sa.String(20), nullable=False),
        sa.Column("primary_topic_id", sa.String(20), nullable=False),
        sa.Column("topic_weight", sa.JSON, nullable=True),
        sa.Column("concept_ids", sa.JSON, nullable=True),
        sa.Column("what_it_tests", sa.Text, nullable=True),
        sa.Column("prerequisite_ids", sa.JSON, nullable=True),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("evidence_quote", sa.Text, nullable=True),
        sa.Column("raw_response", sa.JSON, nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="suggested"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("question_id", "provider", "model", "prompt_version",
                            name="uq_proposal_provider"),
    )


def downgrade() -> None:
    op.drop_table("classification_proposals")
