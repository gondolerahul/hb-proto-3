"""document memory domain (need-to-know retrieval)

Revision ID: retr003
Revises: retr002
Create Date: 2026-07-22

Increment 2 / RETR — T3. The Inc-1 domain viewport (technical §24.3) enforces
"share knowledge, not habits" over Knowledge and Episodic nodes, but KB
documents carried no domain at all, so the one retrieval path an agent uses most
was outside need-to-know entirely.

``documents.memory_domain`` closes that: a document tagged ``payroll`` cannot
enter the viewport of an agent scoped to ``["crm"]``, however well it ranks.

NULL is the safe default and stays meaningful — the viewport treats an untagged
node as ``general`` (common knowledge), so existing documents keep behaving
exactly as they do today and only explicit tagging narrows anything.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'retr003'
down_revision: Union[str, Sequence[str], None] = 'retr002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents',
                  sa.Column('memory_domain', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'memory_domain')
