"""LEARN stores — pooled observations, KPI history, drift series, preferences

Revision ID: learn001
Revises: fleet001
Create Date: 2026-07-25

Increment 6 / LEARN — T1. Four control-plane tables, one of which is unlike
the others: ``platform_observations`` has **no company_id column**, which is
charter decision 2's "structurally incapable of carrying tenant content" made
literal. Every column there is a FK to a platform catalog row, a member of a
closed vocabulary, a date bucket, or a counter.

The other three (`kpi_snapshots`, `entity_behaviour_weekly`, `user_preferences`)
are ordinary tenant-scoped tables with a NOT NULL company FK.

Design: docs/product-road-map/increment-6/01_learn.md §4, §6, §8, §9.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = 'learn001'
down_revision: Union[str, Sequence[str], None] = 'fleet001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── the pooled path — note what is NOT here: no company_id, no payload,
    # no text column. Adding one would repeal the guarantee decision 8 rests on.
    op.create_table(
        'platform_observations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('metric', sa.String(32), nullable=False),
        sa.Column('model_registry_id', UUID(as_uuid=True),
                  sa.ForeignKey('model_registry.id'), nullable=True),
        sa.Column('task_type', sa.String(64), nullable=False),
        sa.Column('reason', sa.String(16), nullable=False),
        sa.Column('bucket_day', sa.Date(), nullable=False),
        sa.Column('observations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('successes', sa.Float(), nullable=False, server_default='0'),
        sa.Column('latency_ms_sum', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('cost_usd_sum', sa.Numeric(18, 6), nullable=False, server_default='0'),
        sa.Column('contributor_floor_met', sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
    )
    # The grain, as an *expression* index. A plain UniqueConstraint would not
    # hold: model_registry_id is nullable (an un-bound legacy integration still
    # routes, so routing_decisions' column is too), and Postgres treats NULLs as
    # distinct in a unique constraint — which would let the daily job append an
    # unbounded number of identical "no model" buckets instead of upserting one.
    # Coalescing to the nil UUID makes "no model" a single value. Preferred over
    # PG15's NULLS NOT DISTINCT so the schema carries no version floor.
    op.create_index(
        'uq_platform_observation_bucket', 'platform_observations',
        ['metric',
         sa.text("coalesce(model_registry_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
         'task_type', 'reason', 'bucket_day'],
        unique=True)
    op.create_index('ix_platform_observations_metric_day', 'platform_observations',
                    ['metric', 'bucket_day'])

    # ── KPI history. value is nullable because "not measurable" is a real
    # reading and must never be written as zero (the C6 honest-absence rule).
    op.create_table(
        'kpi_snapshots',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('kpi_key', sa.String(64), nullable=False),
        sa.Column('captured_on', sa.Date(), nullable=False),
        sa.Column('value', sa.Numeric(18, 6), nullable=True),
        sa.Column('measurable', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('missing', JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('baseline_value', sa.Numeric(18, 6), nullable=True),
        sa.Column('sample_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('window_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('unit', sa.String(16), nullable=False, server_default='count'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('company_id', 'kpi_key', 'captured_on',
                            name='uq_kpi_snapshot_company_key_day'),
    )
    op.create_index('ix_kpi_snapshots_company_day', 'kpi_snapshots',
                    ['company_id', 'captured_on'])

    op.create_table(
        'entity_behaviour_weekly',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('entity_id', UUID(as_uuid=True),
                  sa.ForeignKey('hierarchical_entities.id'), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('runs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('approval_rate', sa.Float(), nullable=True),
        sa.Column('rejection_rate', sa.Float(), nullable=True),
        sa.Column('escalation_rate', sa.Float(), nullable=True),
        sa.Column('consent_refusal_rate', sa.Float(), nullable=True),
        sa.Column('mean_steps', sa.Float(), nullable=True),
        sa.Column('mean_csat', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('entity_id', 'week_start',
                            name='uq_entity_behaviour_entity_week'),
    )
    op.create_index('ix_entity_behaviour_company_week', 'entity_behaviour_weekly',
                    ['company_id', 'week_start'])

    op.create_table(
        'user_preferences',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('key', sa.String(64), nullable=False),
        sa.Column('value', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('learned', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('user_id', 'key', name='uq_user_preference_user_key'),
    )


def downgrade() -> None:
    op.drop_table('user_preferences')
    op.drop_index('ix_entity_behaviour_company_week', table_name='entity_behaviour_weekly')
    op.drop_table('entity_behaviour_weekly')
    op.drop_index('ix_kpi_snapshots_company_day', table_name='kpi_snapshots')
    op.drop_table('kpi_snapshots')
    op.drop_index('ix_platform_observations_metric_day', table_name='platform_observations')
    op.drop_index('uq_platform_observation_bucket', table_name='platform_observations')
    op.drop_table('platform_observations')
