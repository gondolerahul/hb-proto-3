"""connector bindings — durable per-company MCP connector bindings

Revision ID: conn001
Revises: prag002
Create Date: 2026-07-23

Increment 4 / CONN — T2. The shipped MCP seam bound servers only in memory;
this table makes a binding durable so it survives a restart and holds the
per-company credential (encrypted inline, the IntegrationRegistry pattern).
Rehydration into the live seam is lazy per company (connectors/service.py).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'conn001'
down_revision: Union[str, Sequence[str], None] = 'prag002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'connector_bindings',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('connector_id', sa.String(48), nullable=False),
        sa.Column('transport_config', sa.JSON(), nullable=True),
        sa.Column('tool_allow', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('write_allow', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('encrypted_secret', sa.Text(), nullable=True),
        sa.Column('cost_sku', sa.String(64), nullable=True),
        sa.Column('status', sa.String(12), nullable=False, server_default='active'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('company_id', 'connector_id',
                            name='uq_connector_bindings_company_connector'),
    )


def downgrade() -> None:
    op.drop_table('connector_bindings')
