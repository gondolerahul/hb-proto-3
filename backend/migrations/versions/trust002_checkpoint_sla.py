"""checkpoint_sla

Revision ID: trust002
Revises: trust001
Create Date: 2026-07-20

Increment 2 / TRUST — C3 per-checkpoint HITL SLAs. Each hitl_checkpoint_defs row
gains sla_seconds + on_timeout (auto_park | auto_deny | escalate) instead of one
global 24h rule; backfilled from the per-category policy in CHECKPOINT_SEED so a
payment approval fails safe fast while a marketing email parks and re-raises.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from src.ai.governance.checkpoints import CHECKPOINT_SEED

revision: str = 'trust002'
down_revision: Union[str, Sequence[str], None] = 'trust001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('hitl_checkpoint_defs',
                  sa.Column('sla_seconds', sa.Integer(), nullable=True))
    op.add_column('hitl_checkpoint_defs',
                  sa.Column('on_timeout', sa.String(12), nullable=False,
                            server_default='escalate'))

    # Backfill the seeded rows from the per-category policy.
    defs = sa.table(
        'hitl_checkpoint_defs',
        sa.column('key', sa.String),
        sa.column('sla_seconds', sa.Integer),
        sa.column('on_timeout', sa.String),
    )
    for row in CHECKPOINT_SEED:
        op.execute(
            defs.update()
            .where(defs.c.key == op.inline_literal(row['key']))
            .values(sla_seconds=row['sla_seconds'], on_timeout=row['on_timeout'])
        )


def downgrade() -> None:
    op.drop_column('hitl_checkpoint_defs', 'on_timeout')
    op.drop_column('hitl_checkpoint_defs', 'sla_seconds')
