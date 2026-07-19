"""add_loop_runtime_budget

Revision ID: loop001
Revises: gov001
Create Date: 2026-07-19

Increment 1 / LOOP+ENV (technical doc §17, §20.4, §23.3): the LOOP tier's
runtime table + the one-root-Loop partial index, budget envelopes with the
protected reserve, wallet holds that close the E3 race, and wallet_debt for
graceful mid-run exhaustion.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'loop001'
down_revision: Union[str, Sequence[str], None] = 'gov001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # One root Loop per tenant (§17.1): partial unique index on the root row.
    op.create_index(
        'uq_root_loop_per_company', 'hierarchical_entities', ['company_id'],
        unique=True,
        postgresql_where=sa.text("type = 'LOOP' AND parent_id IS NULL"),
    )

    op.create_table(
        'loop_runtime',
        sa.Column('loop_entity_id', UUID(as_uuid=True), sa.ForeignKey('hierarchical_entities.id'), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('heartbeat_interval_s', sa.Integer(), nullable=False, server_default='120'),
        sa.Column('last_beat_at', sa.DateTime(), nullable=True),
        sa.Column('consecutive_missed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stats', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_loop_runtime_company_id', 'loop_runtime', ['company_id'])

    op.create_table(
        'budget_envelopes',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('entity_id', UUID(as_uuid=True), sa.ForeignKey('hierarchical_entities.id'), nullable=False),
        sa.Column('cycle', sa.String(10), nullable=False, server_default='monthly'),
        sa.Column('envelope_usd', sa.Numeric(12, 4), nullable=False, server_default='0'),
        sa.Column('reserved_usd', sa.Numeric(12, 4), nullable=False, server_default='0'),
        sa.Column('spent_usd', sa.Numeric(12, 4), nullable=False, server_default='0'),
        sa.Column('downshift_at_pct', sa.Integer(), nullable=False, server_default='80'),
        sa.Column('refreshed_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_budget_envelopes_company_id', 'budget_envelopes', ['company_id'])
    op.create_index('ix_budget_envelopes_entity', 'budget_envelopes', ['company_id', 'entity_id'])

    op.create_table(
        'wallet_holds',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('run_id', UUID(as_uuid=True), sa.ForeignKey('execution_runs.id'), nullable=False, unique=True),
        sa.Column('amount_held', sa.Numeric(12, 4), nullable=False),
        sa.Column('amount_spent', sa.Numeric(12, 4), nullable=False, server_default='0'),
        sa.Column('status', sa.String(10), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('settled_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_wallet_holds_company_id', 'wallet_holds', ['company_id'])
    op.create_index('ix_wallet_holds_company_status', 'wallet_holds', ['company_id', 'status'])

    op.add_column('credit_wallets', sa.Column(
        'wallet_debt', sa.Numeric(12, 4), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('credit_wallets', 'wallet_debt')
    op.drop_index('ix_wallet_holds_company_status', table_name='wallet_holds')
    op.drop_index('ix_wallet_holds_company_id', table_name='wallet_holds')
    op.drop_table('wallet_holds')
    op.drop_index('ix_budget_envelopes_entity', table_name='budget_envelopes')
    op.drop_index('ix_budget_envelopes_company_id', table_name='budget_envelopes')
    op.drop_table('budget_envelopes')
    op.drop_index('ix_loop_runtime_company_id', table_name='loop_runtime')
    op.drop_table('loop_runtime')
    op.drop_index('uq_root_loop_per_company', table_name='hierarchical_entities')
