"""Inc 1 / GOV — DB-backed governance core (technical doc §20).

The seeded checkpoint registry and the human_approvals.checkpoint_key column
(the two things the migration adds) work end-to-end. ``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from src.ai.governance.checkpoints import CHECKPOINT_KEYS, MANDATORY_KEYS
from src.ai.governance.models import HITLCheckpointDef

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


class TestCheckpointRegistry:
    async def test_eighteen_checkpoints_seeded(self, db):
        total = (await db.execute(
            select(func.count()).select_from(HITLCheckpointDef)
        )).scalar_one()
        assert total == 18

    async def test_seed_keys_match_fixture(self, db):
        keys = set((await db.execute(select(HITLCheckpointDef.key))).scalars().all())
        assert keys == set(CHECKPOINT_KEYS)

    async def test_mandatory_flags_match_fixture(self, db):
        rows = (await db.execute(
            select(HITLCheckpointDef.key).where(
                HITLCheckpointDef.platform_mandatory.is_(True)
            )
        )).scalars().all()
        assert set(rows) == set(MANDATORY_KEYS)
        assert len(rows) == 10

    async def test_payout_checkpoint_threshold(self, db):
        row = (await db.execute(
            select(HITLCheckpointDef).where(
                HITLCheckpointDef.key == "before_outbound_payout_above_band"
            )
        )).scalar_one()
        assert row.default_threshold == 500.0
        assert row.threshold_unit == "usd"
        assert row.platform_mandatory is True


class TestApprovalCheckpointKey:
    async def test_checkpoint_key_persists_on_human_approval(self, db, test_company_id):
        """The GOV column links an approval to its checkpoint (PolicyGate flow)."""
        from src.ai.orm.entity import HierarchicalEntity
        from src.ai.orm.execution import ExecutionRun, HumanApproval

        entity = HierarchicalEntity(
            company_id=test_company_id, type="AGENT", name="gov-test", status="ACTIVE",
        )
        db.add(entity)
        await db.flush()
        run = ExecutionRun(
            company_id=test_company_id, entity_id=entity.id,
            input_data={}, status="PAUSED",
        )
        db.add(run)
        await db.flush()

        approval = HumanApproval(
            run_id=run.id,
            checkpoint_trigger="policy:payout",
            checkpoint_key="before_outbound_payout_above_band",
            status="PENDING",
            requested_by="policy_gate",
            context_snapshot={"category": "payout", "reason": "A1 requires approval"},
        )
        db.add(approval)
        await db.flush()

        loaded = (await db.execute(
            select(HumanApproval).where(HumanApproval.id == approval.id)
        )).scalar_one()
        assert loaded.checkpoint_key == "before_outbound_payout_above_band"
        assert loaded.checkpoint_trigger == "policy:payout"
