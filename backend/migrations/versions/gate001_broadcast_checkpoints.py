"""broadcast + ad-spend HITL checkpoints — the 20th and 21st, for KAR-05

Revision ID: gate001
Revises: sega002
Create Date: 2026-07-25

Increment 6 / GATE — T1. `src/ai/tools/social/` shipped 64 tools across 16
platforms and not one appeared in ``TOOL_CATEGORY_MAP``, so the PolicyGate
``PASS``ed every public post and every ad-budget commitment at every autonomy
band. T1 adds the two governing categories (`broadcast`, `ad_spend`) and this
migration seeds the two checkpoints they raise.

Two, not one: the design doc named only ``before_public_broadcast``, but
`ad_spend` carries an amount band and borrowing the payout checkpoint would
make an ad campaign un-opt-out-able (payout is platform_mandatory), AUTO_DENY
in 4h instead of 8h, and mislabelled on the card as an outbound payout.

Idempotent, exactly like ``conn002``'s 19th: a fresh DB already has both rows
because ``gov001`` seeds ``CHECKPOINT_SEED`` dynamically (now 21); an existing
DB (seeded at 18 or 19) gets them here. The per-key guard makes every path
converge on exactly one row each.
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'gate001'
down_revision: Union[str, Sequence[str], None] = 'sega002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# key, category, description, default_threshold, threshold_unit, sla_seconds, on_timeout
_ROWS: list[tuple[str, str, str, float | None, str | None, int, str]] = [
    (
        "before_public_broadcast",
        "broadcast",
        "Publishing to a public or semi-public audience (post, public reply, upload).",
        None,
        None,
        86400,
        "auto_park",
    ),
    (
        "before_ad_spend_above_band",
        "ad_spend",
        "Committing budget on an ad platform above the autonomous band.",
        200.0,
        "usd",
        28800,
        "auto_deny",
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    for key, category, descr, threshold, unit, sla, on_timeout in _ROWS:
        exists = bind.execute(
            sa.text("SELECT 1 FROM hitl_checkpoint_defs WHERE key = :k"), {"k": key}
        ).first()
        if exists:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO hitl_checkpoint_defs "
                "(id, key, category, description, default_threshold, threshold_unit, "
                " platform_mandatory, created_at, sla_seconds, on_timeout) "
                "VALUES (:id, :key, :cat, :descr, :thr, :unit, false, now(), :sla, :ot)"
            ),
            {
                "id": str(uuid.uuid4()),
                "key": key,
                "cat": category,
                "descr": descr,
                "thr": threshold,
                "unit": unit,
                "sla": sla,
                "ot": on_timeout,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    for key, *_ in _ROWS:
        bind.execute(
            sa.text("DELETE FROM hitl_checkpoint_defs WHERE key = :k"), {"k": key}
        )
