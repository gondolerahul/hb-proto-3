"""model registry — versioned/region/effective-dated fleet catalog (REG / B12)

Revision ID: reg001
Revises: conn002
Create Date: 2026-07-23

Increment 5 / REG — T1. Closes register B12 (model registry too coarse). Two
control-plane tables:
  * model_registry — the fleet catalog (one model, one region, one version,
    with a capability_profile and a data_flow block). Only status='active' is
    router-eligible.
  * model_prices   — effective-dated pricing. A change closes the open window
    and inserts a new one; billing resolves the window containing the event
    time, so a past invoice is reproducible.
Plus a nullable model_registry_id FK on integration_registry (the per-company
binding; NULL = un-bound legacy row, unchanged behaviour).

Design: docs/product-road-map/increment-5/01_model_registry.md §3.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = 'reg001'
down_revision: Union[str, Sequence[str], None] = 'conn002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'model_registry',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('model_key', sa.String(64), nullable=False, index=True),
        sa.Column('provider', sa.String(32), nullable=False),
        sa.Column('model_name', sa.String(128), nullable=False),
        sa.Column('version', sa.String(48), nullable=False, server_default=''),
        sa.Column('region', sa.String(48), nullable=False, server_default='global'),
        sa.Column('capability_profile', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('data_flow', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('status', sa.String(12), nullable=False, server_default='preview'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('provider', 'model_name', 'version', 'region',
                            name='uq_model_registry_provider_model_version_region'),
    )
    op.create_index('ix_model_registry_status', 'model_registry', ['status'])

    op.create_table(
        'model_prices',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('model_registry_id', UUID(as_uuid=True),
                  sa.ForeignKey('model_registry.id', ondelete='CASCADE'), nullable=False),
        sa.Column('component_type', sa.String(32), nullable=False),
        sa.Column('unit_price', sa.Numeric(18, 6), nullable=False),
        sa.Column('cost_unit', sa.String(32), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('effective_from', sa.DateTime(), nullable=False),
        sa.Column('effective_to', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_model_prices_lookup', 'model_prices',
                    ['model_registry_id', 'component_type', 'effective_from'])

    # The per-company binding: nullable, so every legacy row keeps working
    # un-bound (the router falls through to the shipped single-model path).
    op.add_column('integration_registry',
                  sa.Column('model_registry_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_integration_registry_model_registry',
        'integration_registry', 'model_registry',
        ['model_registry_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_integration_registry_model_registry',
                       'integration_registry', type_='foreignkey')
    op.drop_column('integration_registry', 'model_registry_id')
    op.drop_index('ix_model_prices_lookup', table_name='model_prices')
    op.drop_table('model_prices')
    op.drop_index('ix_model_registry_status', table_name='model_registry')
    op.drop_table('model_registry')
