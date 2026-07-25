"""entity version ledger + run taint level (SEGA)

Revision ID: sega001
Revises: learn001
Create Date: 2026-07-25

Increment 6 / SEGA — T2 and T6.

``entity_versions`` is VG-17: editing an entity overwrites its JSON blocks, so
there was nothing to diff, nothing to roll back to, and nothing for the
Gallery's "every version inspectable" or the Glasshouse's promotion diff to
read. Full snapshots rather than a diff chain — rollback has to work when the
chain is broken, and a diff view needs two complete states anyway.

``execution_runs.taint_level`` is D3's other half: a column rather than a
``context_state`` key because ``context_state`` is rewritten wholesale and an
audit trail has to survive that.

Design: docs/product-road-map/increment-6/02_sega.md §5, §7.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = 'sega001'
down_revision: Union[str, Sequence[str], None] = 'learn001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'entity_versions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_id', UUID(as_uuid=True),
                  sa.ForeignKey('hierarchical_entities.id'), nullable=False, index=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('version', sa.String(32), nullable=False),
        sa.Column('snapshot', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('change_kind', sa.String(24), nullable=False, server_default='human'),
        sa.Column('changed_by_user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),
        # No FK: signals are a different module (the ORM stays import-light),
        # and a signal can be reaped or replayed — a version must outlive the
        # proposal that caused it.
        sa.Column('proposal_signal_id', UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='ga'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('entity_id', 'version', name='uq_entity_version'),
    )
    op.create_index('ix_entity_versions_company_entity_created', 'entity_versions',
                    ['company_id', 'entity_id', 'created_at'])

    # D3 — the run's current trust level, which only ever descends. Nullable
    # because every run that predates this migration has an unknown taint, and
    # "unknown" must not be silently read as "trusted".
    op.add_column('execution_runs',
                  sa.Column('taint_level', sa.String(24), nullable=True))


def downgrade() -> None:
    op.drop_column('execution_runs', 'taint_level')
    op.drop_index('ix_entity_versions_company_entity_created', table_name='entity_versions')
    op.drop_table('entity_versions')
