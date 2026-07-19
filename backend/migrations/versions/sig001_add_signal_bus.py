"""add_signal_bus

Revision ID: sig001
Revises: z9b0c1d2e3f4
Create Date: 2026-07-19

Increment 1 / SIG (technical doc §18): the `signals` outbox table and the
`trigger_registry`. Postgres is the bus — signals are transactional rows
claimed with FOR UPDATE SKIP LOCKED; producer idempotency comes from the
partial unique index on (company_id, dedupe_key).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'sig001'
down_revision: Union[str, Sequence[str], None] = 'z9b0c1d2e3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'signals',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('source', sa.String(30), nullable=False),
        sa.Column('type', sa.String(120), nullable=False),
        sa.Column('urgency', sa.String(10), nullable=False, server_default='normal'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('trust', sa.String(20), nullable=False, server_default='internal'),
        sa.Column('object_refs', sa.JSON(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('dedupe_key', sa.String(255), nullable=True),
        sa.Column('status', sa.String(12), nullable=False, server_default='PENDING'),
        sa.Column('owner_process_id', UUID(as_uuid=True), sa.ForeignKey('hierarchical_entities.id'), nullable=True),
        sa.Column('consumed_by_run_id', UUID(as_uuid=True), sa.ForeignKey('execution_runs.id'), nullable=True),
        sa.Column('park_review_at', sa.DateTime(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('replayed_from', UUID(as_uuid=True), sa.ForeignKey('signals.id'), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_signals_company_id', 'signals', ['company_id'])
    op.create_index(
        'uq_signals_company_dedupe', 'signals', ['company_id', 'dedupe_key'],
        unique=True, postgresql_where=sa.text('dedupe_key IS NOT NULL'),
    )
    op.create_index('ix_signals_status_created', 'signals', ['status', 'created_at'])
    op.create_index('ix_signals_company_status', 'signals', ['company_id', 'status'])

    op.create_table(
        'trigger_registry',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('process_entity_id', UUID(as_uuid=True), sa.ForeignKey('hierarchical_entities.id'), nullable=False),
        sa.Column('type_pattern', sa.String(120), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_trigger_registry_company_id', 'trigger_registry', ['company_id'])
    op.create_index(
        'ix_trigger_registry_company_enabled', 'trigger_registry',
        ['company_id', 'enabled'],
    )


def downgrade() -> None:
    op.drop_index('ix_trigger_registry_company_enabled', table_name='trigger_registry')
    op.drop_index('ix_trigger_registry_company_id', table_name='trigger_registry')
    op.drop_table('trigger_registry')
    op.drop_index('ix_signals_company_status', table_name='signals')
    op.drop_index('ix_signals_status_created', table_name='signals')
    op.drop_index('uq_signals_company_dedupe', table_name='signals')
    op.drop_index('ix_signals_company_id', table_name='signals')
    op.drop_table('signals')
