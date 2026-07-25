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

from src.ai.solo_pack.templates import SOLO_PACK_TEMPLATES
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
            for tbl in ("pragya_delegations", "pragya_turns", "pragya_engagements",
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

    assert deployed["activated"]
    assert deployed["entity_count"] == len(SOLO_PACK_TEMPLATES)

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


# --- advancement on a live engagement (Inc-4 PRAGYA-RT T3) -------------------

async def test_a_gathering_stage_advances_once_its_artifacts_are_complete(pragya_tenant):
    """Stage 1 gathers; nothing was agreed, so nothing needs confirming."""
    from src.ai.pragya.advancement import evaluate_eligibility
    from src.ai.pragya.scripts import script_for_stage
    from src.common.database import AsyncSessionLocal

    script = script_for_stage(1)
    cid, _ = pragya_tenant

    async with AsyncSessionLocal() as db:
        engagement = await get_or_create_engagement(db, cid)
        assert not evaluate_eligibility(Stage.BASELINE, engagement.artifacts).eligible

        await record_artifacts(db, engagement, {
            k: (["x"] if k != script.primary_artifact else "a services business")
            for k in script.artifacts})
        await db.commit()

        result = evaluate_eligibility(Stage.BASELINE, engagement.artifacts)
        assert result.eligible and not result.needs_confirmation

        await advance(db, engagement, reason="artifacts complete")
        await db.commit()
        assert current_stage(engagement) is Stage.ASSUMPTIONS


async def test_an_agreement_stage_waits_for_the_owner(pragya_tenant):
    """Stage 2's deliverable is the owner's review, so complete artifacts make
    it eligible but must not move it."""
    from src.ai.pragya.advancement import evaluate_eligibility, needs_owner_confirmation
    from src.ai.pragya.scripts import script_for_stage
    from src.common.database import AsyncSessionLocal

    script = script_for_stage(2)
    cid, _ = pragya_tenant

    async with AsyncSessionLocal() as db:
        engagement = await get_or_create_engagement(db, cid)
        await set_stage(db, engagement, Stage.ASSUMPTIONS, reason="test")
        await record_artifacts(db, engagement, {
            k: (["a1", "a2"] if k == script.primary_artifact else [])
            for k in script.artifacts})
        await db.commit()

        result = evaluate_eligibility(Stage.ASSUMPTIONS, engagement.artifacts)
        assert result.eligible
        assert result.needs_confirmation
        assert needs_owner_confirmation(Stage.ASSUMPTIONS)
        # Eligible is not advanced — the engagement has not moved.
        assert current_stage(engagement) is Stage.ASSUMPTIONS


async def test_artifacts_from_an_earlier_stage_survive_re_extraction(pragya_tenant):
    """Extraction is additive: a re-entered stage refines, never erases."""
    from src.common.database import AsyncSessionLocal

    cid, _ = pragya_tenant
    async with AsyncSessionLocal() as db:
        engagement = await get_or_create_engagement(db, cid)
        await record_artifacts(db, engagement, {
            "baseline.research_summary": "first pass",
            "baseline.gaps": ["headcount"],
        })
        await record_artifacts(db, engagement, {
            "baseline.research_summary": "corrected pass",
        })
        await db.commit()

    async with AsyncSessionLocal() as db:
        engagement = await get_or_create_engagement(db, cid)
        assert engagement.artifacts["baseline.research_summary"] == "corrected pass"
        assert engagement.artifacts["baseline.gaps"] == ["headcount"]


# --- delegation: dispatch, promise, report (Inc-4 PRAGYA-RT T4) --------------

async def test_delegating_records_a_promise_the_platform_can_be_held_to(pragya_tenant):
    from src.ai.pragya.delegation import DelegationKind, delegate, pending_for
    from src.common.database import AsyncSessionLocal

    cid, _ = pragya_tenant
    async with AsyncSessionLocal() as db:
        promise = await delegate(
            db, company_id=cid, kind=DelegationKind.RESEARCH,
            subject="your pricing", stage=Stage.BASELINE)
        await db.commit()

    assert "your pricing" in promise.promise
    async with AsyncSessionLocal() as db:
        outstanding = await pending_for(db, cid)
    assert len(outstanding) == 1
    assert outstanding[0].kind == DelegationKind.RESEARCH
    assert outstanding[0].reported_at is None


async def test_a_capability_build_without_a_meta_agent_refuses_rather_than_promises(
    pragya_tenant,
):
    """An unkept promise costs more trust than an honest 'I can't'."""
    from src.ai.pragya.delegation import DelegationKind, delegate
    from src.common.database import AsyncSessionLocal

    cid, _ = pragya_tenant
    async with AsyncSessionLocal() as db:
        with pytest.raises(ValueError, match="Meta-Agent"):
            await delegate(db, company_id=cid,
                           kind=DelegationKind.CAPABILITY_BUILD,
                           subject="a payroll reconciler")
        await db.rollback()


async def test_a_capability_build_dispatches_a_run_against_the_board(pragya_tenant):
    """Pragya starting the board must be indistinguishable from a signal
    starting it — same run shape, no second entry point."""
    from src.ai.orm.entity import HierarchicalEntity
    from src.ai.orm.execution import ExecutionRun
    from src.ai.pragya.delegation import DelegationKind, delegate
    from src.common.database import AsyncSessionLocal

    cid, _ = pragya_tenant
    async with AsyncSessionLocal() as db:
        board = HierarchicalEntity(
            company_id=cid, name="meta-agent-board", display_name="Meta Agent",
            type="AGENT", status="ACTIVE")
        db.add(board)
        await db.commit()
        board_id = board.id

    try:
        async with AsyncSessionLocal() as db:
            promise = await delegate(
                db, company_id=cid, kind=DelegationKind.CAPABILITY_BUILD,
                subject="a payroll reconciler")
            await db.commit()

        assert promise.run_id is not None
        async with AsyncSessionLocal() as db:
            run = (await db.execute(
                select(ExecutionRun).where(
                    ExecutionRun.id == promise.run_id))).scalars().one()
        assert run.entity_id == board_id
        assert run.status == "PENDING"
        assert run.input_data["channel"] == "pragya"
        assert "payroll reconciler" in run.input_data["input"]
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM pragya_delegations WHERE company_id = :c"),
                             {"c": str(cid)})
            await db.execute(text("DELETE FROM execution_runs WHERE company_id = :c"),
                             {"c": str(cid)})
            await db.execute(text("DELETE FROM hierarchical_entities WHERE id = :e"),
                             {"e": str(board_id)})
            await db.commit()


async def test_finished_work_is_reported_once_and_only_once(pragya_tenant):
    from src.ai.pragya.delegation import (
        DelegationKind,
        complete,
        delegate,
        mark_reported,
        unreported_for,
    )
    from src.common.database import AsyncSessionLocal

    cid, _ = pragya_tenant
    async with AsyncSessionLocal() as db:
        promise = await delegate(
            db, company_id=cid, kind=DelegationKind.RESEARCH,
            subject="your website")
        await db.commit()
        delegation_id = promise.id

    # Nothing to report while it is still running.
    async with AsyncSessionLocal() as db:
        assert await unreported_for(db, cid) == []

    async with AsyncSessionLocal() as db:
        await complete(db, delegation_id, {"summary": "a services business"})
        await db.commit()

    async with AsyncSessionLocal() as db:
        outstanding = await unreported_for(db, cid)
        assert len(outstanding) == 1
        await mark_reported(db, outstanding)
        await db.commit()

    # Reported once: a second turn must not repeat it.
    async with AsyncSessionLocal() as db:
        assert await unreported_for(db, cid) == []


async def test_failed_work_is_surfaced_not_swallowed(pragya_tenant):
    from src.ai.pragya.delegation import DelegationKind, delegate, fail, unreported_for
    from src.common.database import AsyncSessionLocal

    cid, _ = pragya_tenant
    async with AsyncSessionLocal() as db:
        promise = await delegate(
            db, company_id=cid, kind=DelegationKind.RESEARCH, subject="your filings")
        await db.commit()

    async with AsyncSessionLocal() as db:
        await fail(db, promise.id, "no search provider configured")
        await db.commit()

    async with AsyncSessionLocal() as db:
        outstanding = await unreported_for(db, cid)
    assert len(outstanding) == 1
    assert outstanding[0].error == "no search provider configured"


async def test_the_confirm_endpoint_is_the_only_way_past_stage_two(pragya_tenant):
    """The console had no way to call this, so the engagement dead-ended at
    stage 2. Pins the contract the fixed console depends on."""
    from src.ai.pragya.advancement import evaluate_eligibility
    from src.ai.pragya.scripts import script_for_stage
    from src.common.database import AsyncSessionLocal

    cid, _ = pragya_tenant
    script = script_for_stage(2)

    async with AsyncSessionLocal() as db:
        engagement = await get_or_create_engagement(db, cid)
        await set_stage(db, engagement, Stage.ASSUMPTIONS, reason="test")
        await db.commit()

    # Incomplete: confirming must be refused, or a half-formed hypothesis is
    # carried into the configuration stage 6 builds from.
    async with AsyncSessionLocal() as db:
        engagement = await get_or_create_engagement(db, cid)
        assert not evaluate_eligibility(Stage.ASSUMPTIONS, engagement.artifacts).eligible

        await record_artifacts(db, engagement, {
            k: (["a1"] if k == script.primary_artifact else [])
            for k in script.artifacts})
        await db.commit()

    # Complete: eligible, needs confirmation, and does not move on its own.
    async with AsyncSessionLocal() as db:
        engagement = await get_or_create_engagement(db, cid)
        result = evaluate_eligibility(Stage.ASSUMPTIONS, engagement.artifacts)
        assert result.eligible and result.needs_confirmation
        assert current_stage(engagement) is Stage.ASSUMPTIONS

        # The owner's action is what moves it.
        await advance(db, engagement, reason="owner confirmed the stage")
        await db.commit()
        assert current_stage(engagement) is Stage.INGESTION


# --- child-entity delegation (Inc-4 T9, decision 6) --------------------------

async def test_a_tenant_with_no_children_gets_no_capability_tool(pragya_tenant):
    from src.ai.pragya.children import available_children, child_schemas
    from src.common.database import AsyncSessionLocal

    cid, _ = pragya_tenant
    async with AsyncSessionLocal() as db:
        children = await available_children(db, cid)
    assert child_schemas(children) == []


async def test_children_are_the_entities_parented_to_pragya(pragya_tenant):
    """Her surface is her colleagues — and only hers, not the whole roster."""
    from src.ai.orm.entity import HierarchicalEntity
    from src.ai.pragya.children import available_children
    from src.common.database import AsyncSessionLocal

    cid, _ = pragya_tenant
    async with AsyncSessionLocal() as db:
        pragya = HierarchicalEntity(
            company_id=cid, name="pragya", display_name="Pragya",
            type="AGENT", status="ACTIVE")
        db.add(pragya)
        await db.flush()
        db.add(HierarchicalEntity(
            company_id=cid, name="meta-agent-board", display_name="Meta Agent",
            type="AGENT", status="ACTIVE", parent_id=pragya.id))
        # Not hers: a Solo Pack worker somewhere else in the tree.
        db.add(HierarchicalEntity(
            company_id=cid, name="agt-038-ar", display_name="AR Agent",
            type="AGENT", status="ACTIVE"))
        await db.commit()

    async with AsyncSessionLocal() as db:
        children = await available_children(db, cid)

    handles = {c.handle for c in children}
    assert "meta_agent_board" in handles
    assert "agt_038_ar" not in handles, "reached an entity that is not her child"


async def test_asking_a_colleague_dispatches_a_run_under_that_child(pragya_tenant):
    """Calling a child IS dispatching a run — tools and delegation are one
    mechanism, and the child's own governance applies from there."""
    from src.ai.orm.entity import HierarchicalEntity
    from src.ai.orm.execution import ExecutionRun
    from src.ai.pragya.delegation import DelegationKind, delegate
    from src.common.database import AsyncSessionLocal

    cid, _ = pragya_tenant
    async with AsyncSessionLocal() as db:
        child = HierarchicalEntity(
            company_id=cid, name="deep-research", display_name="Deep Research",
            type="AGENT", status="ACTIVE")
        db.add(child)
        await db.commit()
        child_id = child.id

    async with AsyncSessionLocal() as db:
        entity = await db.get(HierarchicalEntity, child_id)
        promise = await delegate(
            db, company_id=cid, kind=DelegationKind.COLLEAGUE,
            subject="your pricing", task="Find their published price list",
            entity=entity, stage=Stage.BASELINE)
        await db.commit()

    assert promise.run_id is not None
    assert "your pricing" in promise.promise

    async with AsyncSessionLocal() as db:
        run = (await db.execute(
            select(ExecutionRun).where(
                ExecutionRun.id == promise.run_id))).scalars().one()
    assert run.entity_id == child_id
    assert run.input_data["channel"] == "pragya"
    assert "price list" in run.input_data["input"]
