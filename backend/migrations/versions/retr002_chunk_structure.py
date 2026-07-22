"""chunk heading context + version

Revision ID: retr002
Revises: retr001
Create Date: 2026-07-22

Increment 2 / RETR — T2 structure-aware chunking (technical §24.4). Chunks gain
the heading trail they were extracted under, and the chunking version they were
produced by.

``chunk_version`` is what makes the **lazy** re-chunk possible (decision 1):
existing rows backfill to 1 (the flat 500-char split), new ingests write
``CURRENT_CHUNK_VERSION``, and a bounded background sweep upgrades stale
documents over time. No big-bang re-embed of every tenant's KB at deploy — which
would be both a large one-off bill and a long window of degraded retrieval.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'retr002'
down_revision: Union[str, Sequence[str], None] = 'retr001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('document_chunks',
                  sa.Column('heading_path', sa.String(), nullable=True))
    op.add_column('document_chunks',
                  sa.Column('chunk_version', sa.Integer(),
                            nullable=False, server_default='1'))
    # The sweep's only query is "documents with stale chunks" — index for it.
    op.create_index('ix_document_chunks_version', 'document_chunks',
                    ['chunk_version'])


def downgrade() -> None:
    op.drop_index('ix_document_chunks_version', table_name='document_chunks')
    op.drop_column('document_chunks', 'chunk_version')
    op.drop_column('document_chunks', 'heading_path')
