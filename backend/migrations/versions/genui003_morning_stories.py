"""The morning stories store

Revision ID: genui003
Revises: genui002
Create Date: 2026-07-29

Inc-7 LINE L2 (13_line.md §5). One table, and the reason it exists at all
is owner decision 2: the story's text is a projection, but pre-generated
daily **audio** cannot be projected for free. Clips ride the row (base64
inside ``cards``) — thirty days ephemeral, per-tenant-private, one
authenticated read path. Retention is reaped inside the producing job.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = 'genui003'
down_revision: Union[str, Sequence[str], None] = 'genui002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "morning_stories",
        sa.Column("company_id", UUID(as_uuid=True),
                  sa.ForeignKey("companies.id"), primary_key=True),
        sa.Column("story_date", sa.Date(), primary_key=True),
        sa.Column("cards", JSONB(), nullable=False),
        sa.Column("degraded_reason", sa.String(80), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("morning_stories")
