"""classification ensemble columns (v6)

Adds agreement, combo_score, provider_votes, provider_count to classifications.
Additive only; existing rows keep NULLs (displayed as single-provider
suggestions until a v6 classification run fills them).

Idempotent for the same reason as 0002: on a fresh database 0001's
create_all() already built these columns from the current models.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("agreement", sa.Float),
    ("combo_score", sa.Float),
    ("provider_votes", sa.JSON),
    ("provider_count", sa.Integer),
)

def _existing() -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns("classifications")}

def upgrade() -> None:
    have = _existing()
    for name, typ in _COLUMNS:
        if name not in have:
            op.add_column("classifications", sa.Column(name, typ(), nullable=True))

def downgrade() -> None:
    have = _existing()
    for name, _ in reversed(_COLUMNS):
        if name in have:
            op.drop_column("classifications", name)
