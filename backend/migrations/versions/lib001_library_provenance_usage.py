"""Library provenance + the retrieval-usage log

Revision ID: lib001
Revises: gate001
Create Date: 2026-07-25

Increment 6 / LIB — T1 + T2, pulled forward ahead of the rest of the workstream
because both are time series and a time series started later cannot be
backfilled: every week without the usage log is a week of influence data that
simply does not exist.

**T1** adds ten provenance columns to `documents`. Existing rows backfill to
`source_kind='upload'` with everything else NULL, which is the honest answer —
we do not know where they came from, and SEGA's taint ladder reads absent
provenance as `external_verified` rather than `internal` for exactly that
reason.

**T2** adds `retrieval_usages`. The query *text* is deliberately not a column.

T3–T8 (`document_influence_daily`, `artifacts.document_id`/`record_ref`,
`connector_bindings.credentials_expire_at`) are **not** in this migration.
06_lib.md §9 scoped them all to `lib001`, but shipping tables nothing writes to
is dead schema that reads as a built feature; they land with the tasks that
use them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'lib001'
down_revision: Union[str, Sequence[str], None] = 'gate001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── T1: provenance on documents ──────────────────────────────────
    # server_default on the two NOT NULL columns is what backfills the
    # existing rows in one statement; the ORM carries the same defaults so a
    # fresh insert and a backfilled row agree.
    op.add_column("documents", sa.Column(
        "source_kind", sa.String(24), nullable=False, server_default="upload"))
    op.add_column("documents", sa.Column("source_uri", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("external_ref", sa.String(255), nullable=True))
    op.add_column("documents", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column(
        "ingested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("documents", sa.Column(
        "ingested_by_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("documents", sa.Column("effective_from", sa.Date(), nullable=True))
    op.add_column("documents", sa.Column(
        "superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("documents", sa.Column(
        "staleness_state", sa.String(16), nullable=False, server_default="fresh"))
    op.add_column("documents", sa.Column(
        "staleness_reason", sa.String(255), nullable=True))

    op.create_foreign_key(
        "fk_documents_ingested_by_user", "documents", "users",
        ["ingested_by_user_id"], ["id"])
    op.create_foreign_key(
        "fk_documents_ingested_by_run", "documents", "execution_runs",
        ["ingested_by_run_id"], ["id"])
    # Self-reference: a superseded document points at the one that replaced it
    # and is kept, never deleted — that is what makes "was this true in March?"
    # answerable at all.
    op.create_foreign_key(
        "fk_documents_superseded_by", "documents", "documents",
        ["superseded_by_id"], ["id"])

    # ── T2: the retrieval-usage log ──────────────────────────────────
    op.create_table(
        "retrieval_usages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("document_chunks.id"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("hierarchical_entities.id"), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("execution_runs.id"), nullable=True),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_retrieval_usages_company_id", "retrieval_usages", ["company_id"])
    op.create_index("ix_retrieval_usages_document_id", "retrieval_usages", ["document_id"])
    op.create_index("ix_retrieval_usages_used_at", "retrieval_usages", ["used_at"])
    # The rollup groups by document and day; the reaper deletes by age. Without
    # this the reaper degrades to a sequential scan over the largest table LIB
    # creates, which is exactly the table that grows fastest.
    op.create_index(
        "ix_retrieval_usages_doc_day", "retrieval_usages", ["document_id", "used_at"])


def downgrade() -> None:
    op.drop_index("ix_retrieval_usages_doc_day", table_name="retrieval_usages")
    op.drop_index("ix_retrieval_usages_used_at", table_name="retrieval_usages")
    op.drop_index("ix_retrieval_usages_document_id", table_name="retrieval_usages")
    op.drop_index("ix_retrieval_usages_company_id", table_name="retrieval_usages")
    op.drop_table("retrieval_usages")

    op.drop_constraint("fk_documents_superseded_by", "documents", type_="foreignkey")
    op.drop_constraint("fk_documents_ingested_by_run", "documents", type_="foreignkey")
    op.drop_constraint("fk_documents_ingested_by_user", "documents", type_="foreignkey")
    for column in (
        "staleness_reason", "staleness_state", "superseded_by_id", "effective_from",
        "ingested_by_run_id", "ingested_by_user_id", "content_hash", "external_ref",
        "source_uri", "source_kind",
    ):
        op.drop_column("documents", column)
