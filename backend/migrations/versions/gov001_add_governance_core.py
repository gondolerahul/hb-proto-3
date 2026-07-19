"""add_governance_core

Revision ID: gov001
Revises: sig001
Create Date: 2026-07-19

Increment 1 / GOV (technical doc §20.2): the `hitl_checkpoint_defs` registry
seeded with the Blueprint §9.7 catalog (18 checkpoints), and the
`human_approvals.checkpoint_key` column linking an approval to its checkpoint.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

from src.ai.governance.checkpoints import CHECKPOINT_SEED

revision: str = 'gov001'
down_revision: Union[str, Sequence[str], None] = 'sig001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'human_approvals',
        sa.Column('checkpoint_key', sa.String(80), nullable=True),
    )

    defs = op.create_table(
        'hitl_checkpoint_defs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('key', sa.String(80), nullable=False, unique=True),
        sa.Column('category', sa.String(40), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('default_threshold', sa.Float(), nullable=True),
        sa.Column('threshold_unit', sa.String(8), nullable=True),
        sa.Column('platform_mandatory', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_hitl_checkpoint_defs_category', 'hitl_checkpoint_defs', ['category'])

    now = datetime.utcnow()
    op.bulk_insert(defs, [
        {
            "id": uuid.uuid4(),
            "key": row["key"],
            "category": row["category"],
            "description": row["description"],
            "default_threshold": row["default_threshold"],
            "threshold_unit": row["threshold_unit"],
            "platform_mandatory": row["platform_mandatory"],
            "created_at": now,
        }
        for row in CHECKPOINT_SEED
    ])


def downgrade() -> None:
    op.drop_index('ix_hitl_checkpoint_defs_category', table_name='hitl_checkpoint_defs')
    op.drop_table('hitl_checkpoint_defs')
    op.drop_column('human_approvals', 'checkpoint_key')
