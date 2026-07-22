"""chunk full-text index (hybrid retrieval)

Revision ID: retr001
Revises: trust004
Create Date: 2026-07-22

Increment 2 / RETR — T1 hybrid retrieval (technical §24.4). The KB's retrieval
was pure cosine over pgvector, which misses exact terms an embedding blurs away
(part numbers, invoice ids, proper nouns). This adds the lexical half: a GIN
index over ``to_tsvector('english', content)`` on ``document_chunks`` so a
Postgres full-text scan is cheap, and the two rankings fuse by reciprocal-rank
fusion at query time.

An expression index needs no column and no backfill — every existing chunk is
searchable the moment it is built.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'retr001'
down_revision: Union[str, Sequence[str], None] = 'trust004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "ix_document_chunks_content_fts"


def upgrade() -> None:
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_INDEX} ON document_chunks "
        "USING GIN (to_tsvector('english', content))"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
