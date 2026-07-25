"""The Glasshouse — scenario shelf and twin runs

Revision ID: twin001
Revises: lib001
Create Date: 2026-07-25

Increment 6 / TWIN — T3. Two control-plane tables and nothing else.

The twin *plane* is deliberately **not** here: tenant tables are bootstrapped
per tenant rather than migrated (SCH, Inc 1), and the twin is a sibling schema
created by the same bootstrap (`t_<hex>_tw`). There is no DDL for it to run.

Off `lib001` rather than `sega001` as the design predicted — GATE and LIB both
landed first, so the chain is `sega002 -> gate001 -> lib001 -> twin001`. The
`entity_version_id` FK into SEGA's ledger is what the design actually cared
about, and `sega001` is an ancestor either way.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'twin001'
down_revision: Union[str, Sequence[str], None] = 'lib001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "twin_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("levers", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("scope", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("acknowledged_estimate_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_twin_scenarios_company_id", "twin_scenarios", ["company_id"])

    op.create_table(
        "twin_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id"), nullable=False),
        # Nullable on purpose: a cached baseline replay belongs to no single
        # scenario, which is what lets every scenario reuse it (§6.2).
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("twin_scenarios.id"), nullable=True),
        sa.Column("grade", sa.String(16), nullable=False),
        sa.Column("method", sa.String(255), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_baseline", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("entity_version_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entity_versions.id"), nullable=True),
        sa.Column("refusal_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_twin_runs_company_id", "twin_runs", ["company_id"])
    op.create_index("ix_twin_runs_company_started", "twin_runs",
                    ["company_id", "started_at"])
    op.create_index("ix_twin_runs_baseline", "twin_runs", ["company_id", "is_baseline"])


def downgrade() -> None:
    op.drop_index("ix_twin_runs_baseline", table_name="twin_runs")
    op.drop_index("ix_twin_runs_company_started", table_name="twin_runs")
    op.drop_index("ix_twin_runs_company_id", table_name="twin_runs")
    op.drop_table("twin_runs")
    op.drop_index("ix_twin_scenarios_company_id", table_name="twin_scenarios")
    op.drop_table("twin_scenarios")
