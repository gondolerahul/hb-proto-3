"""external-write HITL checkpoint — the 19th, for SOR write-back

Revision ID: conn002
Revises: conn001
Create Date: 2026-07-23

Increment 4 / CONN+SOR — T3. Writing back to an external system of record (§21)
is a governed act class the original 18 checkpoints did not cover; this seeds
the 19th (`before_external_system_write`, category external_write, AUTO_PARK 24h).

Idempotent: a fresh DB already has the row because gov001 seeds
``CHECKPOINT_SEED`` dynamically (now 19); an existing DB (seeded at 18) gets it
here. The guard makes both paths converge on exactly one row.
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'conn002'
down_revision: Union[str, Sequence[str], None] = 'conn001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KEY = "before_external_system_write"


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM hitl_checkpoint_defs WHERE key = :k"), {"k": _KEY}
    ).first()
    if exists:
        return
    bind.execute(
        sa.text(
            "INSERT INTO hitl_checkpoint_defs "
            "(id, key, category, description, default_threshold, threshold_unit, "
            " platform_mandatory, created_at, sla_seconds, on_timeout) "
            "VALUES (:id, :key, :cat, :descr, NULL, NULL, false, now(), 86400, 'auto_park')"
        ),
        {
            "id": str(uuid.uuid4()),
            "key": _KEY,
            "cat": "external_write",
            "descr": "Writing back to an external system of record via a connector (SOR, §21).",
        },
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM hitl_checkpoint_defs WHERE key = :k"), {"k": _KEY}
    )
