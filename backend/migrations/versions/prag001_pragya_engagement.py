"""pragya engagement state + conversation turns

Revision ID: prag001
Revises: iauth001
Create Date: 2026-07-22

Increment 3 / PRAGYA — T1. One engagement row per company holding where the
nine-stage flow has reached and everything it has learned, plus the turn log.

``artifacts`` and ``stage_history`` are JSONB rather than typed tables on
purpose: their keys are declared by the stage scripts, which are reviewed
assets meant to evolve. A column per artifact would make every script revision
a migration.

Turns are persisted because the engagement spans months and channels — a
conversation started in the console continues on WhatsApp, and stage 4's
re-entry needs to know what was already said.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = 'prag001'
down_revision: Union[str, Sequence[str], None] = 'iauth001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pragya_engagements',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('stage', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('artifacts', JSONB(), nullable=False, server_default='{}'),
        sa.Column('stage_history', JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id', name='uq_pragya_engagement_company'),
    )

    op.create_table(
        'pragya_turns',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('stage', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(12), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('intent_kind', sa.String(40), nullable=True),
        sa.Column('tier', sa.String(4), nullable=True),
        sa.Column('outcome', sa.String(24), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('pragya_turns')
    op.drop_table('pragya_engagements')
