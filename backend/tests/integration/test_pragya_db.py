"""Inc-3 PRAGYA — engagement persistence and the exit-demo path. ``needs_db``.

The pure halves (stage rules, intent tiers, KPI formulas, demotion triggers)
are pinned in ``tests/unit``. What needs a database is the part that spans
them: an engagement that walks the stages, a command that actually flips
triggers, and the guarantee that Pragya's activation produces the same tenant
the wizard would.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.governance.demotion_sweep import apply_demotions
from src.ai.inward_auth.models import AuthLevel, ChannelKind
from src.ai.inward_auth.sessions import elevate, get_or_create_session
from src.ai.kpi.compute import compute_all
from src.ai.pragya.commands import execute_command
from src.ai.pragya.deployment import deploy_bundle, propose_blueprint
from src.ai.pragya.engagement import (
    advance,
    current_stage,
    get_or_create_engagement,
    record_artifacts,
    record_turn,
    recent_turns,
    set_stage,
)
from src.ai.pragya.intents import classify_turn
from src.ai.pragya.stages import Stage, TransitionError
from src.ai.signals.models import TriggerRegistration
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def pragya_tenant():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid, uid = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"pragya-test-{cid.hex[:8]}"})
        await s.execute(
            text("INSERT INTO users (id, email, full_name, hashed_password, company_id, "
                 "role, is_active, is_verified, created_at, updated_at) "
                 "VALUES (:id, :e, 'Pragya Test Owner', 'x', :c, 'tenant_admin', "
                 "true, true, now(), now())"),
            {"id": str(uid), "e": f"pragya-{uid.hex[:8]}@example.test", "c": str(cid)})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    try:
        yield cid, uid
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            for tbl in ("pragya_turns", "pragya_engagements",
                        "account_manager_sessions", "channel_bindings",
                        "trigger_registry", "budget_envelopes", "loop_runtime",
                        "wallet_holds", "signals", "execution_runs"):
                await s.execute(
                    text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(
                text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                {"c": str(cid)})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


# --- engagement persistence ---------------------------------------------------

async def test_engagement_opens_at_stage_one_and_is_idempotent(pragya_tenant):
    cid, _ = pragya_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        first = await get_or_create_engagement(db, cid)
        await db.commit()
        first_id = first.id
        assert current_stage(first) is Stage.BASELINE

    async with AsyncSessionLocal() as db:
        second = await get_or_create_engagement(db, cid)
        await db.commit()
    assert second.id == first_id


async def test_stage_history_records_why_each_move_happened(pragya_tenant):
    cid, _ = pragya_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        engagement = await get_or_create_engagement(db, cid)
        await advance(db, engagement, reason="owner corrected the research")
        await advance(db, engagement, reason="assumptions reviewed")
        await db.commit()
        assert current_stage(engagement) is Stage.INGESTION
        reasons = [h.get("reason") for h in engagement.stage_history]
        assert "assumptions reviewed" in reasons


async def test_skipping_a_stage_is_refused(pragya_tenant):
    cid, _ = pragya_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        engagement = await get_or_create_engagement(db, cid)
        with pytest.raises(TransitionError):
            await set_stage(db, engagement, Stage.DEPLOY, reason="impatient")
        await db.rollback()


async def test_re_entry_from_operate_preserves_earlier_artifacts(pragya_tenant):
    """Stages 4-6 re-enter to *add* evidence, never to start over."""
    cid, _ = pragya_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        engagement = await get_or_create_engagement(db, cid)
        await record_artifacts(db, engagement, {
            "baseline.research_summary": "a services business",
            "assumptions.list": ["inbound-led"],
        })
        for stage in list(Stage)[1:]:
            await set_stage(db, engagement, stage, reason="walk")
        await set_stage(db, engagement, Stage.ANALYSIS, reason="quarterly re-test")
        await record_artifacts(db, engagement, {"analysis.verdicts": ["confirmed"]})
        await db.commit()

    async with AsyncSessionLocal() as db:
        engagement = await get_or_create_engagement(db, cid)
        assert current_stage(engagement) is Stage.ANALYSIS
        # Stage 1's work survived the loop back.
        assert engagement.artifacts["baseline.research_summary"] == "a services business"
        assert engagement.artifacts["analysis.verdicts"] == ["confirmed"]


async def test_turns_persist_in_conversation_order(pragya_tenant):
    cid, uid = pragya_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        for i, (role, text_) in enumerate(
                [("user", "hello"), ("pragya", "hi"), ("user", "how did we do?")]):
            await record_turn(db, company_id=cid, stage=Stage.OPERATE,
                              role=role, content=text_, user_id=uid)
        await db.commit()

    async with AsyncSessionLocal() as db:
        turns = await recent_turns(db, cid)
    assert [t.content for t in turns] == ["hello", "hi", "how did we do?"]


# --- the exit-demo command path ----------------------------------------------

async def test_pause_command_requires_elevation_then_flips_triggers(pragya_tenant):
    """The exit demo: 'pause invoice chasing' is T2, needs a step-up, and
    actually disarms triggers once elevated."""
    cid, uid = pragya_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await deploy_bundle(db, cid, "solo_pack", user_id=uid)
        await db.commit()

    command = classify_turn("pause invoice chasing while I'm away", None)
    assert command.tier.name == "T2"

    # A merely-bound session cannot run it.
    async with AsyncSessionLocal() as db:
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        await db.commit()
        blocked = await execute_command(db, session, command, company_id=cid)
        assert not blocked.executed

    # Elevated but with no resolvable target, she asks rather than pausing
    # the whole workforce — an unscoped pause must never resolve to "all".
    async with AsyncSessionLocal() as db:
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        await elevate(db, session, method="passkey")
        vague = await execute_command(db, session, command, company_id=cid)
        await db.commit()
    assert not vague.executed
    assert "which one" in vague.message.lower()

    async with AsyncSessionLocal() as db:
        still_on = (await db.execute(
            select(TriggerRegistration).where(
                TriggerRegistration.company_id == cid,
                TriggerRegistration.enabled.is_(True))
        )).scalars().all()
    assert still_on, "an ambiguous pause disarmed the workforce"

    # With the process named, it runs and scopes to that process alone.
    targeted = classify_turn(
        "pause invoice chasing",
        {"kind": "process_pause", "target": "Order-to-Cash",
         "summary": "pause invoice chasing"})
    async with AsyncSessionLocal() as db:
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        await elevate(db, session, method="passkey")
        outcome = await execute_command(db, session, targeted, company_id=cid)
        await db.commit()

    assert outcome.executed
    assert outcome.changed and outcome.changed["triggers_changed"] >= 1
    async with AsyncSessionLocal() as db:
        remaining = (await db.execute(
            select(TriggerRegistration).where(
                TriggerRegistration.company_id == cid,
                TriggerRegistration.enabled.is_(True))
        )).scalars().all()
    # The named process is disarmed; the rest of the workforce keeps running.
    assert len(remaining) >= 1


async def test_kill_switch_disarms_everything(pragya_tenant):
    cid, uid = pragya_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await deploy_bundle(db, cid, "solo_pack", user_id=uid)
        await db.commit()

    command = classify_turn("stop everything right now", None)
    assert command.tier.name == "T3"

    async with AsyncSessionLocal() as db:
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        await elevate(db, session, method="passkey",
                      level=AuthLevel.OOB_CONFIRMED)
        outcome = await execute_command(db, session, command, company_id=cid)
        await db.commit()

    assert outcome.executed
    async with AsyncSessionLocal() as db:
        enabled = (await db.execute(
            select(TriggerRegistration).where(
                TriggerRegistration.company_id == cid,
                TriggerRegistration.enabled.is_(True))
        )).scalars().all()
    assert enabled == []


# --- stages 6-9 over the wizard APIs -----------------------------------------

async def test_pragya_activation_equals_the_wizard_output(pragya_tenant):
    """Decision 4: one contract. If these diverge, the console wizard and the
    conversation produce different tenants from the same choice."""
    cid, uid = pragya_tenant
    from src.ai.solo_pack.onboarding import onboarding_status
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        deployed = await deploy_bundle(db, cid, "solo_pack", user_id=uid)
        await db.commit()

    assert deployed["activated"] and deployed["entity_count"] == 18

    async with AsyncSessionLocal() as db:
        wizard_status = await onboarding_status(db, cid)
    assert wizard_status["entity_count"] == deployed["status"]["entity_count"]
    assert wizard_status["trigger_count"] == deployed["status"]["trigger_count"]


async def test_blueprint_preview_shows_a1_before_anything_activates(pragya_tenant):
    blueprint = await propose_blueprint("solo_pack")
    governance = blueprint["governance"]

    seeded = [
        *governance["gateways"],
        *(e for group in governance["processes"]
          for e in (group["process"], *group["agents"])),
    ]
    assert seeded, "the preview showed no entities at all"
    # Nothing may be previewed above A1 — the owner must not be shown a
    # configuration that acts without them.
    assert all(e["autonomy_level"] == "A1" for e in seeded)
    assert "A1" in blueprint["autonomy_note"]


# --- C6 reporting on a live tenant -------------------------------------------

async def test_a_fresh_tenant_reports_no_fabricated_kpis(pragya_tenant):
    """Day one: every business KPI is honestly unmeasurable, not zero."""
    cid, _ = pragya_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        results = await compute_all(db, cid)

    business = [r for r in results if r.key != "agent_hitl_load"]
    assert business
    for reading in business:
        assert not reading.measurable, f"{reading.key} invented {reading.value}"
        assert reading.missing


# --- C4 sweep on a live tenant -----------------------------------------------

async def test_demotion_sweep_is_quiet_on_a_healthy_tenant(pragya_tenant):
    """A tenant that has run nothing must not have its workforce demoted."""
    cid, uid = pragya_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await deploy_bundle(db, cid, "solo_pack", user_id=uid)
        await db.commit()

    async with AsyncSessionLocal() as db:
        verdicts = await apply_demotions(db, cid)
        await db.commit()

    assert verdicts, "sweep evaluated no agents at all"
    assert not any(v.demote for v in verdicts)
