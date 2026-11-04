"""widen provider/model/prompt_version columns (PostgreSQL enforces VARCHAR length)

Found by running the full test suite on PostgreSQL 17: `auto` and ensemble
classification runs store composite values ("auto:gemini+openrouter",
"modelA+modelB+modelC") that exceeded VARCHAR(20)/(60). SQLite never enforced
the length, so this only fails on Postgres - on the first real multi-provider
run. Widening a VARCHAR is lossless and idempotent. SQLite needs no change.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_WIDEN = (
    ("classification_runs", "model", 300),
    ("classification_runs", "provider", 120),
    ("classification_runs", "prompt_version", 40),
    ("classifications", "model", 300),
    ("classifications", "prompt_version", 40),
    ("processing_runs", "model", 300),
)

def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite does not enforce VARCHAR length
    insp = sa.inspect(bind)
    for table, column, width in _WIDEN:
        cols = {c["name"]: c for c in insp.get_columns(table)}
        cur = getattr(cols[column]["type"], "length", None)
        if cur is not None and cur < width:
            op.alter_column(table, column, type_=sa.String(width), existing_nullable=cols[column]["nullable"])

def downgrade() -> None:
    # Narrowing could truncate data; intentionally a no-op.
    pass
