"""add onboarding and phone pool

Revision ID: a1b2c3d4e5f6
Revises: None
Create Date: 2026-05-05

Adds:
  - onboarding_status, onboarding_metadata, default_daily_credits to companies
  - phone_number_pool table
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Companies: add onboarding columns ---
    op.add_column('companies', sa.Column('onboarding_status', sa.String(), server_default='pending'))
    op.add_column('companies', sa.Column('onboarding_metadata', postgresql.JSONB(), nullable=True))
    op.add_column('companies', sa.Column('default_daily_credits', sa.String(), nullable=True))

    # --- Phone Number Pool table ---
    op.create_table(
        'phone_number_pool',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('phone_number', sa.String(20), unique=True, nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('country_code', sa.String(5), nullable=False, server_default='+91'),
        sa.Column('status', sa.String(20), server_default='available'),
        sa.Column('label', sa.String(100), nullable=True),
        sa.Column('claimed_by_company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=True),
        sa.Column('claimed_at', sa.DateTime(), nullable=True),
        sa.Column('claimed_by_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('monthly_cost_usd', sa.Numeric(10, 4), nullable=True),
        sa.Column('provider_sid', sa.String(100), nullable=True),
        sa.Column('capabilities', postgresql.JSONB(), nullable=True),
        sa.Column('added_by_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('notes', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('phone_number_pool')
    op.drop_column('companies', 'default_daily_credits')
    op.drop_column('companies', 'onboarding_metadata')
    op.drop_column('companies', 'onboarding_status')
