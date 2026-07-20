"""subscription_status

Revision ID: trust004
Revises: trust003
Create Date: 2026-07-20

Increment 2 / TRUST — C5 graduated dunning. Adds companies.subscription_status
(current → past_due → grace → read_only → suspended) so the state-aware
suspension middleware can degrade access gracefully instead of a cliff. Existing
companies backfill to 'current'.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'trust004'
down_revision: Union[str, Sequence[str], None] = 'trust003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('companies',
                  sa.Column('subscription_status', sa.String(),
                            nullable=False, server_default='current'))


def downgrade() -> None:
    op.drop_column('companies', 'subscription_status')
