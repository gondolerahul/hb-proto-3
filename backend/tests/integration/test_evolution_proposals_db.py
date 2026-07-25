"""SEGA T7 + T8 — LEARN proposes, SEGA disposes, end to end (closes B11).

Until T7 existed, `blast_radius.admit_change` was a guarantee with no caller.
B11 asks what *forbids* a self-heal from mutating a global artifact; the answer
is only real once something is routed through it. These tests are that
something.

The cases that matter are the refusals — and that each refusal is **visible**:
a parked signal carrying its reason, because a silent refusal and a silent bug
look identical from outside.

``needs_db``.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


def _db_url():
    import os

    from src.common.config import settings
    return getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")


async def _make_company(status: str = "current") -> uuid.UUID:
    from src.common.database import AsyncSessionLocal

    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, subscription_status, "
                 "created_at, updated_at) VALUES "
                 "(:id, :n, 'TENANT', 'active', :ss, now(), now())"),
            {"id": str(cid), "n": f"prop-{cid.hex[:8]}", "ss": status})
        await s.commit()
    return cid


async def _make_entity(cid: uuid.UUID) -> uuid.UUID:
    from src.common.database import AsyncSessionLocal

    eid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO hierarchical_entities (id, company_id, version, type, "
                 "status, name, display_name, goal, governance, created_at, updated_at) "
                 "VALUES (:i, :c, '1.0.0', 'AGENT', 'ACTIVE', :n, :n, "
                 "'answer the customer', CAST(:g AS json), now(), now())"),
            {"i": str(eid), "c": str(cid), "n": f"prop-agent-{eid.hex[:6]}",
             "g": json.dumps({"autonomy_level": "A2"})})
        await s.commit()
    return eid


async def _proposal(cid: uuid.UUID, eid: uuid.UUID, *, field="goal",
                    addition="Be clearer.", evidence: int = 3) -> uuid.UUID:
    """A `learning.charter_tuning_proposed` signal, as LEARN would emit it."""
    from src.ai.learning.tuning import TuningProposal, emit_proposal
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        signal_id = await emit_proposal(
            db, company_id=cid,
            proposal=TuningProposal(
                entity_id=eid, field=field, addition=addition,
                evidence_observations=evidence,
                rationale=f"{evidence} observations"))
        await db.commit()
    assert signal_id is not None
    return signal_id


async def _drop(cid: uuid.UUID) -> None:
    from src.common.database import AsyncSessionLocal, engine

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
    async with AsyncSessionLocal() as s:
        for tbl in ("signals", "entity_versions", "execution_runs",
                    "hierarchical_entities"):
            await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"),
                            {"c": str(cid)})
        await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
        await s.commit()


@pytest_asyncio.fixture
async def tenant():
    if not _db_url():
        pytest.skip("DATABASE_URL not set")
    from src.common.database import engine

    await engine.dispose()
    cid = await _make_company()
    eid = await _make_entity(cid)
    try:
        yield SimpleNamespace(company_id=cid, entity_id=eid)
    finally:
        await _drop(cid)
        tenant_data_plane.reset_cache()


# ── T7 · the happy path ──────────────────────────────────────────────────────

async def test_a_proposal_becomes_a_canary_version(tenant):
    """The end-to-end shape: signal → admitted → applied → recorded as canary.

    Recorded as `canary`, not `ga`: the change is live, and the sweep decides
    later whether it stays.
    """
    from src.ai.evolution.proposals import consume_proposals
    from src.common.database import AsyncSessionLocal

    signal_id = await _proposal(tenant.company_id, tenant.entity_id)

    async with AsyncSessionLocal() as db:
        summary = await consume_proposals(db, tenant.company_id)

    assert summary["applied"] == 1
    assert summary["refused"] == []

    async with AsyncSessionLocal() as db:
        row = (await db.execute(text(
            "SELECT change_kind, status, proposal_signal_id::text FROM entity_versions "
            "WHERE entity_id = :e"), {"e": str(tenant.entity_id)})).one()
        assert row.change_kind == "charter_tune"
        assert row.status == "canary"
        assert row.proposal_signal_id == str(signal_id)

        consumed = (await db.execute(text(
            "SELECT status FROM signals WHERE id = :i"), {"i": str(signal_id)})).scalar()
        assert consumed == "CONSUMED"


async def test_the_addition_appends_rather_than_replaces(tenant):
    """A learning proposal adds to what a colleague was told; it does not
    rewrite it. Replacing a goal an owner wrote with a sentence a loop inferred
    is exactly the overreach the field allow-list exists to bound."""
    from src.ai.evolution.proposals import consume_proposals
    from src.common.database import AsyncSessionLocal

    await _proposal(tenant.company_id, tenant.entity_id, addition="Also cite sources.")

    async with AsyncSessionLocal() as db:
        await consume_proposals(db, tenant.company_id)

    async with AsyncSessionLocal() as db:
        goal = (await db.execute(text(
            "SELECT goal FROM hierarchical_entities WHERE id = :e"),
            {"e": str(tenant.entity_id)})).scalar()

    assert "answer the customer" in goal, "the owner's original words must survive"
    assert "Also cite sources." in goal


# ── T7 · the refusals, and their visibility ──────────────────────────────────

async def test_a_governance_field_is_refused_and_the_signal_is_parked(tenant):
    """The B11 refusal that matters most — and it is *visible*.

    LEARN cannot phrase this proposal and SEGA will not apply it. Constructed
    by hand here precisely because the honest test of a refusal is one that
    bypasses the producer that is supposed to make it impossible.
    """
    from src.ai.evolution.proposals import consume_proposals
    from src.common.database import AsyncSessionLocal
    from src.ai.signals.models import SignalSource, SignalTypes
    from src.ai.signals.service import emit_signal

    async with AsyncSessionLocal() as db:
        signal_id = await emit_signal(
            db, company_id=tenant.company_id, source=SignalSource.TELEMETRY,
            type=SignalTypes.LEARNING_CHARTER_TUNING_PROPOSED,
            payload={"entity_id": str(tenant.entity_id), "field": "governance",
                     "addition": '{"autonomy_level": "A4"}'},
            dedupe_key=f"hand-built-{uuid.uuid4()}")
        await db.commit()

    async with AsyncSessionLocal() as db:
        summary = await consume_proposals(db, tenant.company_id)

    assert summary["applied"] == 0
    assert any("governance" in r for r in summary["refused"])

    async with AsyncSessionLocal() as db:
        row = (await db.execute(text(
            "SELECT status, last_error FROM signals WHERE id = :i"),
            {"i": str(signal_id)})).one()
    assert row.status == "PARKED"
    assert "governance" in row.last_error, (
        "a refusal a human cannot see is indistinguishable from a bug")

    async with AsyncSessionLocal() as db:
        band = (await db.execute(text(
            "SELECT governance FROM hierarchical_entities WHERE id = :e"),
            {"e": str(tenant.entity_id)})).scalar()
    assert band["autonomy_level"] == "A2", "the band must not have moved"


async def test_a_proposal_naming_another_tenants_entity_changes_nothing(tenant):
    """Scope first, then act — the predicate is the second layer, not the only
    one. A stranger's entity id finds nothing to change."""
    from src.ai.evolution.proposals import consume_proposals
    from src.common.database import AsyncSessionLocal

    stranger = await _make_company()
    stranger_entity = await _make_entity(stranger)
    try:
        await _proposal(tenant.company_id, stranger_entity)

        async with AsyncSessionLocal() as db:
            summary = await consume_proposals(db, tenant.company_id)

        assert summary["applied"] == 0
        assert any("not" in r for r in summary["refused"])

        async with AsyncSessionLocal() as db:
            goal = (await db.execute(text(
                "SELECT goal FROM hierarchical_entities WHERE id = :e"),
                {"e": str(stranger_entity)})).scalar()
        assert goal == "answer the customer"
    finally:
        await _drop(stranger)


async def test_a_suspended_tenant_admits_no_automated_change(tenant):
    """A tenant who has stopped paying should not discover their workforce
    rewrote itself while they were away."""
    from src.ai.evolution.proposals import consume_proposals
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "UPDATE companies SET subscription_status = 'suspended' WHERE id = :c"),
            {"c": str(tenant.company_id)})
        await db.commit()

    await _proposal(tenant.company_id, tenant.entity_id)

    async with AsyncSessionLocal() as db:
        summary = await consume_proposals(db, tenant.company_id)

    assert summary["applied"] == 0
    assert any("suspended" in r for r in summary["refused"])


async def test_the_daily_cap_stops_the_fourth_change(tenant):
    """Counted from the ledger, not a counter: a counter can drift from what
    actually happened, and the limit is about what actually happened."""
    from src.ai.evolution.proposals import consume_proposals
    from src.common.database import AsyncSessionLocal

    # Distinct evidence counts, because `emit_proposal` dedupes on
    # (entity, field, evidence) — five identical proposals are one proposal, by
    # design, so the cap would never be reached with a repeated one.
    for i in range(5):
        await _proposal(tenant.company_id, tenant.entity_id,
                        addition=f"Tip {i}.", evidence=3 + i)

    async with AsyncSessionLocal() as db:
        summary = await consume_proposals(db, tenant.company_id)

    assert summary["applied"] == 3, "the default cap is three a day"
    assert len(summary["refused"]) == 2
    assert all("already today" in r for r in summary["refused"])


# ── T8 · agent-proposed fields ───────────────────────────────────────────────

async def test_an_agent_proposed_field_lands_on_the_object(tenant):
    """No DDL: a tenant object's fields are a JSONB list and its records are
    JSONB documents, so an addition is an append and a version bump."""
    from src.ai.evolution.schema_proposals import apply_field_proposal
    from src.ai.tenant_schema.data_plane import tenant_data_plane

    await tenant_data_plane.ensure_ready(tenant.company_id)

    # Read through the ORM, not raw SQL: `schema_translate_map` rewrites the
    # symbolic `tenant` schema only for Table/ORM constructs, so a text() query
    # would look for an unqualified `tenant_entity_defs` and not find it.
    from sqlalchemy import select

    from src.ai.tenant_schema.models import TenantEntityDef

    async with tenant_data_plane.session(tenant.company_id) as tdb:
        def_query = select(TenantEntityDef).where(
            TenantEntityDef.company_id == tenant.company_id,
            TenantEntityDef.name == "Quote")

        before = (await tdb.execute(def_query)).scalar_one()
        before_version, before_count = before.version, len(before.fields or [])

        descriptor = await apply_field_proposal(
            tdb, company_id=tenant.company_id, object_name="Quote",
            proposed={"name": "competitor_quoted", "type": "money"})
        await tdb.commit()

    async with tenant_data_plane.session(tenant.company_id) as tdb:
        after = (await tdb.execute(def_query)).scalar_one()

        assert descriptor["name"] == "competitor_quoted"
        assert after.version == before_version + 1
        assert len(after.fields) == before_count + 1
        assert any(f["name"] == "competitor_quoted" for f in after.fields)


async def test_a_field_addition_is_refused_for_a_frozen_tenant(tenant):
    """The same blast-radius limits as a charter tune — one predicate, not two."""
    from src.ai.evolution.blast_radius import BlastRadiusError
    from src.ai.evolution.schema_proposals import apply_field_proposal
    from src.ai.tenant_schema.data_plane import tenant_data_plane

    await tenant_data_plane.ensure_ready(tenant.company_id)

    async with tenant_data_plane.session(tenant.company_id) as tdb:
        with pytest.raises(BlastRadiusError, match="read_only"):
            await apply_field_proposal(
                tdb, company_id=tenant.company_id, object_name="Quote",
                proposed={"name": "whatever", "type": "string"},
                subscription_status="read_only")
        await tdb.rollback()


async def test_an_unknown_object_is_refused(tenant):
    from src.ai.evolution.schema_proposals import SchemaProposalError, apply_field_proposal
    from src.ai.tenant_schema.data_plane import tenant_data_plane

    await tenant_data_plane.ensure_ready(tenant.company_id)

    async with tenant_data_plane.session(tenant.company_id) as tdb:
        with pytest.raises(SchemaProposalError, match="no object named"):
            await apply_field_proposal(
                tdb, company_id=tenant.company_id, object_name="Nonexistent",
                proposed={"name": "f", "type": "string"})
        await tdb.rollback()
