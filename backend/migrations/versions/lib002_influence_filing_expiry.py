"""Library influence rollup, artifact filing, connector credential expiry

Revision ID: lib002
Revises: twin001
Create Date: 2026-07-26

Increment 6 / LIB — T3, T5 and T8. These are the three schema changes `lib001`
deliberately left out ([06_lib.md](../../docs/product-road-map/increment-6/06_lib.md)
§13.2): shipping a table nothing writes to is dead schema that reads as a built
feature, so each lands with the task that uses it.

**T3** `document_influence_daily` — what survives the 30-day reaper, and what
the influence panel actually reads. Three counters rather than the design's
two: `retrievals` counts rows, and only `distinct_queries` answers "how many
questions did this document help answer" (a single question can return three
chunks of the same document).

**T5** `artifacts.document_id` + `artifacts.record_ref` — the artifact store
joins the Library. `record_ref` is JSON with no FK on purpose: records live in
the tenant data plane and this row does not.

**T8** `connector_bindings.credentials_expire_at` — VG-16. NULL means no known
expiry, which is the honest state of an API key that has none.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'lib002'
down_revision: Union[str, Sequence[str], None] = 'twin001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── T3: the daily influence rollup ───────────────────────────────
    op.create_table(
        "document_influence_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # Present although document_id implies it: reading a tenant's panel
        # without this column means joining `documents` to scope every read,
        # and a scoping rule that depends on remembering a join is the exact
        # shape of the VG-05 IDOR and SEGA T0's tool-registry disclosure.
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("retrievals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("distinct_queries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("distinct_entities", sa.Integer(), nullable=False, server_default="0"),
        # No nullable column in the grain, so ordinary conflict inference works
        # and a day can be re-rolled in place — LEARN needed a `coalesce`
        # expression index for exactly the opposite reason.
        sa.UniqueConstraint("document_id", "day", name="uq_doc_influence_doc_day"),
    )
    op.create_index("ix_document_influence_daily_company_id",
                    "document_influence_daily", ["company_id"])
    op.create_index("ix_document_influence_daily_document_id",
                    "document_influence_daily", ["document_id"])
    op.create_index("ix_document_influence_daily_day",
                    "document_influence_daily", ["day"])

    # ── T5: artifacts join the Library ───────────────────────────────
    op.add_column("artifacts", sa.Column(
        "document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("artifacts", sa.Column(
        "record_ref", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.create_foreign_key(
        "fk_artifacts_document", "artifacts", "documents",
        ["document_id"], ["id"])

    # ── T8: VG-16 credential expiry ──────────────────────────────────
    op.add_column("connector_bindings", sa.Column(
        "credentials_expire_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("connector_bindings", "credentials_expire_at")

    op.drop_constraint("fk_artifacts_document", "artifacts", type_="foreignkey")
    op.drop_column("artifacts", "record_ref")
    op.drop_column("artifacts", "document_id")

    op.drop_index("ix_document_influence_daily_day",
                  table_name="document_influence_daily")
    op.drop_index("ix_document_influence_daily_document_id",
                  table_name="document_influence_daily")
    op.drop_index("ix_document_influence_daily_company_id",
                  table_name="document_influence_daily")
    op.drop_table("document_influence_daily")
