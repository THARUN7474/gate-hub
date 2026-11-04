"""initial schema + PostgreSQL-only extras (pgvector extension, FTS index)

Revision ID: 0001
"""
from alembic import op
from sqlalchemy import engine_from_config

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    from src.db.models import Base
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    if bind.dialect.name == "postgresql":
        # pgvector is expected from the pgvector/pgvector:pg17 Docker image. If a
        # different Postgres runtime lacks the extension, continue WITHOUT it and
        # say so loudly - embeddings are optional Phase-1 work, but this must
        # never be mistaken for pgvector being installed.
        try:
            op.execute("CREATE EXTENSION IF NOT EXISTS vector")
            print("pgvector extension: ENABLED")
        except Exception as e:  # noqa: BLE001
            print(f"WARNING: pgvector extension NOT available in this Postgres ({e}). "
                  "Schema + FTS still applied; embeddings need the pgvector Docker image.")
        # Full-text search over question text (structured filters stay B-tree).
        op.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS search_tsv tsvector "
                   "GENERATED ALWAYS AS (to_tsvector('english', coalesce(text,''))) STORED")
        op.execute("CREATE INDEX IF NOT EXISTS ix_questions_fts ON questions USING GIN (search_tsv)")
        # NOTE: no vector embedding column yet. pgvector's vector type is added
        # by a follow-up migration once the embedding model (and its dimension)
        # is chosen - per the Phase 1 plan, embeddings are optional Day-5 work.

def downgrade() -> None:
    from src.db.models import Base
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_questions_fts")
        op.execute("ALTER TABLE questions DROP COLUMN IF EXISTS search_tsv")
    Base.metadata.drop_all(bind)
