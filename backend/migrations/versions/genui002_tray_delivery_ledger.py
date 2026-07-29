"""The tray delivery ledger and the recommendation store

Revision ID: genui002
Revises: genui001
Create Date: 2026-07-29

Inc-7 STEWARD S1/S2 (12_steward.md §4–§5). Two tables:

* ``tray_deliveries`` — one row per (approval, user) actually reached, via
  socket or push. The unique pair is the whole design: restart-safe
  once-only delivery, *and* late-arriving devices still hear about
  still-pending cards because no row exists for that pair yet.
* ``tray_recommendations`` — Pragya's one advisory sentence per tray,
  written once at first delivery (approval id is the primary key: one card,
  one sentence, no history). Outside the certified block by construction.

No tenant-plane DDL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'genui002'
down_revision: Union[str, Sequence[str], None] = 'genui001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tray_deliveries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("approval_id", UUID(as_uuid=True),
                  sa.ForeignKey("human_approvals.id"), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True),
                  sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("via", sa.String(16), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "approval_id", "user_id", name="uq_tray_deliveries_approval_user"),
    )
    op.create_index(
        "ix_tray_deliveries_approval_id", "tray_deliveries", ["approval_id"])
    op.create_index(
        "ix_tray_deliveries_company_id", "tray_deliveries", ["company_id"])

    op.create_table(
        "tray_recommendations",
        sa.Column("approval_id", UUID(as_uuid=True),
                  sa.ForeignKey("human_approvals.id"), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True),
                  sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("sentence", sa.String(500), nullable=False),
        sa.Column("model_used", sa.String(120), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_tray_recommendations_company_id",
        "tray_recommendations", ["company_id"])


def downgrade() -> None:
    op.drop_index(
        "ix_tray_recommendations_company_id", table_name="tray_recommendations")
    op.drop_table("tray_recommendations")
    op.drop_index("ix_tray_deliveries_company_id", table_name="tray_deliveries")
    op.drop_index("ix_tray_deliveries_approval_id", table_name="tray_deliveries")
    op.drop_table("tray_deliveries")
