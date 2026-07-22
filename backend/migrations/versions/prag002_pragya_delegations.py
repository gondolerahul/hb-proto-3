"""pragya delegations — promised work that outlives a turn

Revision ID: prag002
Revises: voice001
Create Date: 2026-07-22

Increment 4 / PRAGYA-RT — T4. Anything longer than a conversational turn is
dispatched, promised, and reported: a Meta-Agent board build, stage-1 deep
research, a bulk ingest. This table is the promise.

It exists because "I'm having that built — a few minutes" must be a claim the
platform can be held to, not a sentence a model produced. ``reported_at`` is
deliberately separate from ``completed_at``: work that finished and was never
reported back is the specific failure this table makes visible, and it is
invisible if one column serves both.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = 'prag002'
down_revision: Union[str, Sequence[str], None] = 'voice001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pragya_delegations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('kind', sa.String(40), nullable=False),
        sa.Column('status', sa.String(12), nullable=False,
                  server_default='promised', index=True),
        sa.Column('promise', sa.Text(), nullable=False),
        sa.Column('params', JSONB(), nullable=False, server_default='{}'),
        sa.Column('result', JSONB(), nullable=True),
        sa.Column('run_id', UUID(as_uuid=True),
                  sa.ForeignKey('execution_runs.id'), nullable=True),
        sa.Column('stage', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('reported_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('pragya_delegations')
