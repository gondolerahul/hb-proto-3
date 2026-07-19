"""seed_sheel

Revision ID: loop002
Revises: loop001
Create Date: 2026-07-19

Increment 1 / LOOP T1 — seed the one root Loop (Sheel) + its loop_runtime +
default budget envelope for every existing tenant. Explicit, visible, auditable
(decision 2026-07-19). Idempotent: companies that already have a root Loop are
skipped. New companies get Sheel lazily via ``ensure_sheel``.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'loop002'
down_revision: Union[str, Sequence[str], None] = 'loop001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    default_envelope = "100.00"
    reserve = "10.00"  # 10% of the default envelope

    companies = conn.execute(sa.text(
        "SELECT c.id FROM companies c WHERE NOT EXISTS ("
        "  SELECT 1 FROM hierarchical_entities e WHERE e.company_id = c.id "
        "  AND e.type = 'LOOP' AND e.parent_id IS NULL AND e.status <> 'ARCHIVED')"
    )).fetchall()

    for (company_id,) in companies:
        loop_id = conn.execute(sa.text(
            "INSERT INTO hierarchical_entities "
            "(id, company_id, version, type, status, name, display_name, description, goal, "
            " governance, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :cid, '1.0.0', 'LOOP', 'ACTIVE', 'Sheel', 'Sheel', "
            " 'The one Loop — the company''s standing top tier.', "
            " 'Turn the six arcs of the business as one governed loop.', "
            " :gov, now(), now()) RETURNING id"),
            {"cid": company_id, "gov": '{"autonomy_level": "A1"}'},
        ).scalar_one()

        conn.execute(sa.text(
            "INSERT INTO loop_runtime "
            "(loop_entity_id, company_id, enabled, heartbeat_interval_s, consecutive_missed, "
            " stats, created_at) "
            "VALUES (:lid, :cid, true, 120, 0, '{}', now())"),
            {"lid": loop_id, "cid": company_id},
        )
        conn.execute(sa.text(
            "INSERT INTO budget_envelopes "
            "(id, company_id, entity_id, cycle, envelope_usd, reserved_usd, spent_usd, "
            " downshift_at_pct, refreshed_at) "
            "VALUES (gen_random_uuid(), :cid, :lid, 'monthly', :env, :res, 0, 80, now())"),
            {"cid": company_id, "lid": loop_id, "env": default_envelope, "res": reserve},
        )


def downgrade() -> None:
    conn = op.get_bind()
    # Remove only platform-seeded Sheel loops (name='Sheel', root).
    loop_ids = conn.execute(sa.text(
        "SELECT id FROM hierarchical_entities "
        "WHERE type = 'LOOP' AND parent_id IS NULL AND name = 'Sheel'"
    )).fetchall()
    for (loop_id,) in loop_ids:
        conn.execute(sa.text("DELETE FROM budget_envelopes WHERE entity_id = :lid"), {"lid": loop_id})
        conn.execute(sa.text("DELETE FROM loop_runtime WHERE loop_entity_id = :lid"), {"lid": loop_id})
        conn.execute(sa.text("DELETE FROM hierarchical_entities WHERE id = :lid"), {"lid": loop_id})
