"""voice handoffs + deferred post-call runs (B7)

Revision ID: voice001
Revises: prag001
Create Date: 2026-07-22

Increment 3 / VOICE — V5/V6. Two tables for the two halves of B7's answer.

``voice_handoffs`` records an agent-to-agent switch on the same media session.
Warm transfer here is not a telephony bridge: the call never moves, only the
entity driving the realtime model changes. The row carries what makes that
invisible to the caller — the transcript gist and the records already
identified — plus the tier ceiling, which is carried rather than recomputed so
that being transferred can never make a caller better authenticated.

``voice_deferred_runs`` queues the stages a live turn could not fit: Strategize,
Pre-Critic, Post-Critic, Reflect, Decide. Nothing is skipped, only moved off
the latency path.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = 'voice001'
down_revision: Union[str, Sequence[str], None] = 'prag001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'voice_handoffs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('call_sid', sa.String(100), nullable=False, index=True),
        sa.Column('from_entity_id', UUID(as_uuid=True),
                  sa.ForeignKey('hierarchical_entities.id'), nullable=True),
        sa.Column('to_entity_id', UUID(as_uuid=True),
                  sa.ForeignKey('hierarchical_entities.id'), nullable=False),
        sa.Column('reason', sa.String(255), nullable=False),
        sa.Column('context_summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('resolved_records', JSONB(), nullable=False, server_default='[]'),
        sa.Column('tier_ceiling', sa.String(4), nullable=False, server_default='T1'),
        sa.Column('caller_user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table(
        'voice_deferred_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('call_sid', sa.String(100), nullable=False, index=True),
        sa.Column('entity_id', UUID(as_uuid=True),
                  sa.ForeignKey('hierarchical_entities.id'), nullable=True),
        sa.Column('status', sa.String(12), nullable=False,
                  server_default='pending', index=True),
        sa.Column('transcript', JSONB(), nullable=False, server_default='[]'),
        sa.Column('stages', JSONB(), nullable=False, server_default='[]'),
        sa.Column('execution_run_id', UUID(as_uuid=True),
                  sa.ForeignKey('execution_runs.id'), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('voice_deferred_runs')
    op.drop_table('voice_handoffs')
