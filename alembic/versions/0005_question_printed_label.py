"""questions.printed_label: the label exactly as printed in the paper

Papers before 2022 restart numbering at CS Q.1 after the GA block. The unique
1..65 q_number is kept as the id; printed_label ("GA 5", "CS 12", "Q 56")
records what the paper itself shows, for the review workspace and key checks.
Idempotent (fresh databases already get the column from 0001's create_all).

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

def _has() -> bool:
    return "printed_label" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("questions")}

def upgrade() -> None:
    if not _has():
        op.add_column("questions", sa.Column("printed_label", sa.String(24), nullable=True))

def downgrade() -> None:
    if _has():
        op.drop_column("questions", "printed_label")
