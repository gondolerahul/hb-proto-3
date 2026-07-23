"""company provider opt-in — the auditable D5 disclosure record (FLEET)

Revision ID: fleet001
Revises: rtr001
Create Date: 2026-07-23

Increment 5 / FLEET — T3. GLM (Zhipu), Qwen (Alibaba) and Kimi (Moonshot) are
registered but never default-allowed; a tenant must opt in explicitly, and D5
wants the acceptance auditable (who, when, which disclosure version). Revocable:
revoked_at drops the provider from effective_allow immediately.

Design: docs/product-road-map/increment-5/03_fleet_expansion.md §3.2.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'fleet001'
down_revision: Union[str, Sequence[str], None] = 'rtr001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'company_provider_optin',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('provider', sa.String(32), nullable=False),
        sa.Column('disclosure_version', sa.String(32), nullable=False),
        sa.Column('opted_in_by', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('opted_in_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('company_id', 'provider', name='uq_company_provider_optin'),
    )


def downgrade() -> None:
    op.drop_table('company_provider_optin')
