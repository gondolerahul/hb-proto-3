"""routing decisions — the router's audit trail + the usage-log link (RTR v1)

Revision ID: rtr001
Revises: reg001
Create Date: 2026-07-23

Increment 5 / RTR — v1. Every routed LLM call records which model was chosen,
why, and over which signals; usage_logs gains a nullable routing_decision_id so
a billing line links directly to the decision that produced it. Both nullable
where appropriate — an un-bound integration still routes, a standalone call has
no run.

Design: docs/product-road-map/increment-5/02_router.md §3.1.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = 'rtr001'
down_revision: Union[str, Sequence[str], None] = 'reg001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'routing_decisions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', UUID(as_uuid=True),
                  sa.ForeignKey('execution_runs.id'), nullable=True, index=True),
        sa.Column('step_id', sa.String(128), nullable=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('task_type', sa.String(64), nullable=False),
        sa.Column('model_registry_id', UUID(as_uuid=True),
                  sa.ForeignKey('model_registry.id'), nullable=True),
        sa.Column('reason', sa.String(16), nullable=False),
        sa.Column('signals', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('fallback_used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )

    # The usage line -> decision link (nullable; set only when routing is active).
    op.add_column('usage_logs',
                  sa.Column('routing_decision_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_usage_logs_routing_decision',
        'usage_logs', 'routing_decisions',
        ['routing_decision_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_usage_logs_routing_decision', 'usage_logs', type_='foreignkey')
    op.drop_column('usage_logs', 'routing_decision_id')
    op.drop_table('routing_decisions')
