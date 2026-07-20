"""platform_budget_class

Revision ID: trust003
Revises: trust002
Create Date: 2026-07-20

Increment 2 / TRUST — B13 platform-initiated budget class. Adds budget_class to
budget_envelopes so platform-initiated spend (optimizer/self-healing/meta/
sensing) draws from its own capped envelope and can never starve tenant work.
Existing rows backfill to 'tenant'.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'trust003'
down_revision: Union[str, Sequence[str], None] = 'trust002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('budget_envelopes',
                  sa.Column('budget_class', sa.String(20), nullable=False,
                            server_default='tenant'))
    # The per-(company, entity) index is no longer unique-per-row semantics we
    # rely on; a company now has a tenant + a platform envelope on the same Loop.
    op.create_index('ix_budget_envelopes_class', 'budget_envelopes',
                    ['company_id', 'entity_id', 'budget_class'])


def downgrade() -> None:
    op.drop_index('ix_budget_envelopes_class', table_name='budget_envelopes')
    op.drop_column('budget_envelopes', 'budget_class')
