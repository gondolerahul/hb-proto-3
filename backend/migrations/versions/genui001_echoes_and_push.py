"""The two Vihara tables: the echo log and the push subscriptions

Revision ID: genui001
Revises: iauth002
Create Date: 2026-07-29

Inc-7 SEAM (D5 §6, §7). Deliberately only two tables. The estate and the
trays are projections; the manifests are a Redis cache of a pure function
plus versioned files in git — there is intentionally **no** ``ui_manifests``
table (D4 §5.1), because what audit needs is the certified manifest's hash
on the approval record and on the echo, and both carry one.

* ``ui_echoes`` — L10's sentences, append-only, 90-day retention reaped in
  the producer's own path (the LIB T3 lesson, applied structurally).
* ``push_subscriptions`` — a Web Push subscription as a row in our own
  table, which is what makes L8's single-writer law enforceable in code
  (VG-19, charter decision 7).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = 'genui001'
down_revision: Union[str, Sequence[str], None] = 'iauth002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ui_echoes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True),
                  sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sentence", sa.String(500), nullable=False),
        sa.Column("action_ref", JSONB(), nullable=False),
        sa.Column("manifest_hash", sa.String(80), nullable=True),
        sa.Column("component_id", sa.String(80), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ui_echoes_company_id", "ui_echoes", ["company_id"])
    op.create_index(
        "ix_ui_echoes_company_created", "ui_echoes", ["company_id", "created_at"])

    op.create_table(
        "push_subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True),
                  sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(255), nullable=False),
        sa.Column("auth", sa.String(255), nullable=False),
        sa.Column("ua", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )
    op.create_index(
        "ix_push_subscriptions_company_id", "push_subscriptions", ["company_id"])
    op.create_index(
        "ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_index("ix_push_subscriptions_company_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
    op.drop_index("ix_ui_echoes_company_created", table_name="ui_echoes")
    op.drop_index("ix_ui_echoes_company_id", table_name="ui_echoes")
    op.drop_table("ui_echoes")
