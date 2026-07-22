"""inward-channel authentication (D1: bindings, sessions, passkeys, TOTP)

Revision ID: iauth001
Revises: retr003
Create Date: 2026-07-22

Increment 3 / AUTH — T1. Pragya accepts owner commands over channels whose
identities are spoofable (caller ID, WhatsApp sender, email From). "Pause any
process in one sentence" from a spoofed number is a full-company compromise;
these four tables are what make the inward face verifiable.

``channel_bindings`` answers *who is this*, ``account_manager_sessions`` answers
*how well did they prove it and until when*, and the two credential tables hold
the factors a step-up can consume.

No table carries a default that grants anything: a session is born ``none``,
and a binding without ``verified_at`` is a claim rather than a proof.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'iauth001'
down_revision: Union[str, Sequence[str], None] = 'retr003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'channel_bindings',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('channel_kind', sa.String(20), nullable=False),
        sa.Column('address', sa.String(255), nullable=False),
        sa.Column('label', sa.String(80), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('otp_hash', sa.String(128), nullable=True),
        sa.Column('otp_expires_at', sa.DateTime(), nullable=True),
        sa.Column('otp_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id', 'channel_kind', 'address',
                            name='uq_channel_binding_address'),
    )

    op.create_table(
        'account_manager_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True, index=True),
        sa.Column('channel_kind', sa.String(20), nullable=False),
        sa.Column('channel_address', sa.String(255), nullable=True),
        sa.Column('auth_level', sa.String(20), nullable=False, server_default='none'),
        sa.Column('elevated_until', sa.DateTime(), nullable=True),
        sa.Column('elevated_by', sa.String(20), nullable=True),
        sa.Column('failed_stepups', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.Column('last_activity_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table(
        'webauthn_credentials',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('credential_id', sa.String(512), nullable=False),
        sa.Column('public_key', sa.String(2048), nullable=False),
        sa.Column('sign_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transports', sa.String(120), nullable=True),
        sa.Column('label', sa.String(80), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('credential_id', name='uq_webauthn_credential_id'),
    )

    op.create_table(
        'totp_secrets',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('secret', sa.String(512), nullable=False),
        sa.Column('confirmed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('last_used_slot', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', name='uq_totp_user'),
    )

    # Challenges are server-side and single-use — WebAuthn's replay protection
    # depends on it, and a client-carried token can only be time-boxed.
    op.create_table(
        'webauthn_challenges',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('purpose', sa.String(20), nullable=False),
        sa.Column('challenge', sa.String(512), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # The T3 second-channel leg. FKs to both the session that asked and the
    # binding that must agree, because "a different channel confirmed it" is
    # the claim this table has to be able to prove after the fact.
    op.create_table(
        'oob_confirmations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('session_id', UUID(as_uuid=True),
                  sa.ForeignKey('account_manager_sessions.id'), nullable=False),
        sa.Column('second_binding_id', UUID(as_uuid=True),
                  sa.ForeignKey('channel_bindings.id'), nullable=False),
        sa.Column('command_ref', sa.String(255), nullable=False),
        sa.Column('nonce_hash', sa.String(128), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('oob_confirmations')
    op.drop_table('webauthn_challenges')
    op.drop_table('totp_secrets')
    op.drop_table('webauthn_credentials')
    op.drop_table('account_manager_sessions')
    op.drop_table('channel_bindings')
