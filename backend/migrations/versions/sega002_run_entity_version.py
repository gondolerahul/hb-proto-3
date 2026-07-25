"""attribute a run to the entity version that served it (SEGA canary)

Revision ID: sega002
Revises: sega001
Create Date: 2026-07-25

Increment 6 / SEGA — T3. A canary verdict compares the candidate version's
runs against the incumbent's, which requires knowing which version served
which run.

Recording it beats recomputing it. The cohort split is a deterministic hash, so
in principle the assignment could be re-derived — but only under the fraction
that was in force at the time. Change the fraction and every past run silently
re-assigns, which would quietly rewrite the evidence a rollback decision was
made on. A stored assignment records what actually happened.

No FK: ``entity_versions`` lives in ``ai/evolution`` and ``execution_runs`` in
``ai/orm``, which is imported almost everywhere. An FK would drag the evolution
mappers into every context that touches a run, the same trap ``sega001``'s
``proposal_signal_id`` hit.

Design: docs/product-road-map/increment-6/02_sega.md §6.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'sega002'
down_revision: Union[str, Sequence[str], None] = 'sega001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('execution_runs',
                  sa.Column('entity_version_id', UUID(as_uuid=True), nullable=True))
    op.create_index('ix_execution_runs_entity_version', 'execution_runs',
                    ['entity_version_id'])


def downgrade() -> None:
    op.drop_index('ix_execution_runs_entity_version', table_name='execution_runs')
    op.drop_column('execution_runs', 'entity_version_id')
