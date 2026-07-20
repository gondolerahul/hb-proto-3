"""add_consent_registry

Revision ID: trust001
Revises: loop002
Create Date: 2026-07-20

Increment 2 / TRUST — D6 consent registry (global-neutral, decision 5): the
consent/DNC/unsubscribe store the tenant-managed provider enforces behind the
KAR outbound seam. Control-plane tables (counterparty postures are per-company,
not tenant-DB business records).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'trust001'
down_revision: Union[str, Sequence[str], None] = 'loop002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'consent_records',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('channel_identity', sa.String(255), nullable=False),
        sa.Column('purpose', sa.String(20), nullable=False),
        sa.Column('status', sa.String(12), nullable=False),
        sa.Column('source', sa.String(20), nullable=False, server_default='tenant'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id', 'channel', 'channel_identity', 'purpose',
                            name='uq_consent_identity_purpose'),
    )
    op.create_index('ix_consent_records_company_id', 'consent_records', ['company_id'])

    op.create_table(
        'dnc_entries',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('channel_identity', sa.String(255), nullable=False),
        sa.Column('reason', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id', 'channel', 'channel_identity',
                            name='uq_dnc_identity'),
    )
    op.create_index('ix_dnc_entries_company_id', 'dnc_entries', ['company_id'])

    op.create_table(
        'unsubscribe_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('channel_identity', sa.String(255), nullable=False),
        sa.Column('purpose', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_unsubscribe_log_company_id', 'unsubscribe_log', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_unsubscribe_log_company_id', table_name='unsubscribe_log')
    op.drop_table('unsubscribe_log')
    op.drop_index('ix_dnc_entries_company_id', table_name='dnc_entries')
    op.drop_table('dnc_entries')
    op.drop_index('ix_consent_records_company_id', table_name='consent_records')
    op.drop_table('consent_records')
