"""SEAM T3 — the estate read model over a real activated pack. ``needs_db``.

The composition is the thing under test: districts from the seeded PROCESS
entities, colleagues from their AGENT children, beacons from pending
approvals through the company-scoped join, weather from the states other
subsystems own, halls from the tenant plane. The last test is the probe
test — an unknown district answers exactly like another tenant's, which is
the VG-05 shape this endpoint was designed around.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update

from src.ai.genui.estate import district_view, estate_view
from src.ai.orm.entity import HierarchicalEntity
from src.ai.orm.execution import ExecutionRun, HumanApproval
from src.ai.signals.models import Signal, SignalStatus, TriggerRegistration
from src.ai.solo_pack.activation import activate_solo_pack
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def tenant():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"estate-test-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    try:
        yield cid
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            await s.execute(text(
                "DELETE FROM human_approvals WHERE run_id IN "
                "(SELECT id FROM execution_runs WHERE company_id = :c)"), {"c": str(cid)})
            for tbl in ("execution_runs", "signals", "trigger_registry",
                        "budget_envelopes", "loop_runtime",
                        "consent_records", "dnc_entries", "unsubscribe_log"):
                await s.execute(
                    text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(
                text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                {"c": str(cid)})
            await s.execute(
                text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def _activated(db, cid) -> dict[str, str]:
    return await activate_solo_pack(db, cid)


class TestEstateComposition:
    async def test_the_activated_pack_projects_whole(self, tenant):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await _activated(db, tenant)
        async with AsyncSessionLocal() as db:
            estate = await estate_view(db, tenant)

        codes = {d["process_code"] for d in estate["districts"]}
        assert codes == {"P03", "P06", "P08", "P10", "P14", "P19"}

        quarters = {q["code"]: q["districts"] for q in estate["quarters"]}
        assert quarters["acquisition"] == ["P03"]
        assert sorted(quarters["finance"]) == ["P08", "P10"]

        channels = {g["channel"] for g in estate["gatehouses"]}
        assert channels == {"email", "whatsapp", "voice", "broadcast"}

        p03 = next(d for d in estate["districts"] if d["process_code"] == "P03")
        names = {c["name"] for c in p03["colleagues"]}
        assert len(names) == 2  # AGT-013 + AGT-015, and no gateway among them
        for colleague in p03["colleagues"]:
            assert colleague["autonomy"].startswith("A")
            assert colleague["state"] == "idle"
            assert colleague["hand_raised"] is False

        assert estate["beacons"] == []
        assert all(d["weather"]["state"] == "clear" for d in estate["districts"])
        assert estate["halls"], "the HBS spine should project as halls"
        assert estate["monuments"] == []
        assert estate["estate"]["phase"] in ("day", "night")

    async def test_a_pending_approval_raises_the_hand_and_the_beacon(self, tenant):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await _activated(db, tenant)
            agent_id = uuid.UUID(result["agt-013-inbound-deal-closer"])
            run = ExecutionRun(
                entity_id=agent_id, company_id=tenant, status="RUNNING")
            db.add(run)
            await db.flush()
            db.add(HumanApproval(
                run_id=run.id, checkpoint_trigger="policy_gate",
                checkpoint_key="before_outbound_payout_above_band",
                status="PENDING", requested_at=datetime.utcnow()))
            await db.commit()

        async with AsyncSessionLocal() as db:
            estate = await estate_view(db, tenant)

        assert len(estate["beacons"]) == 1
        beacon = estate["beacons"][0]
        assert beacon["district"] == "P03"
        assert beacon["sla_seconds_left"] is None or beacon["sla_seconds_left"] > 0

        p03 = next(d for d in estate["districts"] if d["process_code"] == "P03")
        hands = {c["name"]: c["hand_raised"] for c in p03["colleagues"]}
        assert any(hands.values())
        raiser = next(c for c in p03["colleagues"] if c["hand_raised"])
        assert raiser["state"] == "running"

    async def test_a_parked_signal_shows_at_both_ends_of_the_road(self, tenant):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await _activated(db, tenant)
            p06_id = uuid.UUID(result["p06-resolve-to-retain"])
            db.add(Signal(
                company_id=tenant, source="whatsapp_inbound",
                type="message.inbound", status=SignalStatus.PARKED,
                owner_process_id=p06_id))
            await db.commit()

        async with AsyncSessionLocal() as db:
            estate = await estate_view(db, tenant)

        p06 = next(d for d in estate["districts"] if d["process_code"] == "P06")
        assert p06["traffic"]["parked"] == 1
        whatsapp = next(
            g for g in estate["gatehouses"] if g["channel"] == "whatsapp")
        assert whatsapp["parked"] == 1
        assert whatsapp["inbound_today"] == 1

    async def test_a_gate_carries_its_consent_posture(self, tenant):
        """D8 E2 — the posture belongs at the door it governs. An unset
        tenant is permissive by Increment 2 decision 8, and the door says so
        in the registry's own words rather than showing nothing."""
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await _activated(db, tenant)
            await db.commit()

        async with AsyncSessionLocal() as db:
            estate = await estate_view(db, tenant)

        email = next(g for g in estate["gatehouses"] if g["channel"] == "email")
        assert email["consent"]["posture"] == "open"
        assert email["consent"]["reason"]
        assert email["consent"] == {
            "posture": "open", "reason": email["consent"]["reason"],
            "dnc": 0, "unsubscribed": 0}

    async def test_a_refused_purpose_shows_at_the_door_with_its_count(self, tenant):
        from src.ai.trust.consent_registry import (
            record_unsubscribe,
            set_channel_posture,
        )
        from src.ai.trust.models import ConsentPurpose, ConsentStatus
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await _activated(db, tenant)
            await set_channel_posture(
                db, tenant, "email", ConsentPurpose.MARKETING, ConsentStatus.DENIED)
            await record_unsubscribe(
                db, tenant, "email", "bye@example.com", ConsentPurpose.MARKETING)
            await db.commit()

        async with AsyncSessionLocal() as db:
            estate = await estate_view(db, tenant)

        email = next(g for g in estate["gatehouses"] if g["channel"] == "email")
        assert email["consent"]["posture"] == "restricted"
        assert "marketing" in email["consent"]["reason"]
        assert email["consent"]["unsubscribed"] == 1
        # The tenant's own switch is a posture, never a counterparty count.
        assert email["consent"]["dnc"] == 0
        # Every other door is untouched by one channel's posture.
        voice = next(g for g in estate["gatehouses"] if g["channel"] == "voice")
        assert voice["consent"]["posture"] == "open"

    async def test_a_hibernating_district_is_moonlit(self, tenant):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await _activated(db, tenant)
            p14_id = uuid.UUID(result["p14-continuous-guardrails"])
            await db.execute(
                update(TriggerRegistration)
                .where(TriggerRegistration.company_id == tenant,
                       TriggerRegistration.process_entity_id == p14_id)
                .values(enabled=False))
            await db.commit()

        async with AsyncSessionLocal() as db:
            estate = await estate_view(db, tenant)

        p14 = next(d for d in estate["districts"] if d["process_code"] == "P14")
        assert p14["weather"]["state"] == "moonlit"
        others = [d for d in estate["districts"] if d["process_code"] != "P14"]
        assert all(d["weather"]["state"] == "clear" for d in others)

    async def test_a_stopped_account_storms_over_every_district(self, tenant):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await _activated(db, tenant)
            await db.execute(
                text("UPDATE companies SET subscription_status = 'read_only' "
                     "WHERE id = :c"), {"c": str(tenant)})
            await db.commit()

        async with AsyncSessionLocal() as db:
            estate = await estate_view(db, tenant)

        assert all(
            d["weather"]["state"] == "storm" for d in estate["districts"])
        assert estate["estate"]["standing"] == "read_only"

    async def test_an_unknown_district_answers_like_a_foreign_one(self, tenant):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await _activated(db, tenant)
        async with AsyncSessionLocal() as db:
            present = await district_view(db, tenant, "P03")
            absent = await district_view(db, tenant, "P99")
        assert present is not None and present["process_code"] == "P03"
        assert absent is None
