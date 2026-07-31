"""Inc-7 D8 E4 — the Talent Office's two reads against real rows. ``needs_db``.

The pure halves are unit-tested next door (``test_talent_brief_read``,
``test_talent_past_cases``). What needs a database is everything the unit
tests have to stub: the tenant-plane join that turns an ``object_refs``
entry into a named record, the four control-plane joins behind ``outcome``,
and the failure a read model is actually likely to have — reading another
tenant's rows.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update

from src.ai.orm.entity import HierarchicalEntity
from src.ai.orm.execution import ExecutionRun, HumanApproval
from src.ai.pragya.models import PragyaDelegation
from src.ai.signals.models import Signal
from src.ai.talent.brief_read import brief_view
from src.ai.talent.past_cases import past_cases_view
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane
from src.ai.tenant_schema.models import TenantEntityDef, TenantRecord
from src.common.config import settings

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

NOW = datetime.utcnow()


async def _make_company(label: str) -> uuid.UUID:
    from src.common.database import AsyncSessionLocal

    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"{label}-{cid.hex[:8]}"})
        await s.commit()
    return cid


async def _drop_company(cid: uuid.UUID) -> None:
    from src.common.database import AsyncSessionLocal, engine

    async with engine.begin() as conn:
        await conn.execute(
            text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
    async with AsyncSessionLocal() as s:
        await s.execute(text(
            "DELETE FROM human_approvals WHERE run_id IN "
            "(SELECT id FROM execution_runs WHERE company_id = :c)"), {"c": str(cid)})
        for tbl in ("signals", "pragya_delegations", "execution_runs",
                    "hierarchical_entities"):
            await s.execute(
                text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
        await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
        await s.commit()


@pytest_asyncio.fixture
async def tenants():
    """Two tenants. The interesting failure of a read model is reading
    someone else's rows, not reading none."""
    import os

    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import engine

    await engine.dispose()
    mine = await _make_company("talent-read")
    theirs = await _make_company("talent-read-other")
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(mine)
    try:
        yield mine, theirs
    finally:
        await _drop_company(mine)
        await _drop_company(theirs)
        tenant_data_plane.reset_cache()


async def _colleague(db, cid: uuid.UUID, name: str) -> uuid.UUID:
    entity = HierarchicalEntity(
        company_id=cid, type="AGENT", status="ACTIVE",
        name=name, display_name=name)
    db.add(entity)
    await db.flush()
    return uuid.UUID(str(entity.id))


async def _handled(
    db, cid: uuid.UUID, entity_id: uuid.UUID, *,
    refs: list[str] | None = None, age_days: int = 2,
) -> tuple[uuid.UUID, uuid.UUID]:
    """A signal that arrived, and the run that answered it."""
    run = ExecutionRun(
        company_id=cid, entity_id=entity_id, status="COMPLETED",
        completed_at=NOW - timedelta(days=age_days))
    db.add(run)
    await db.flush()
    signal = Signal(
        company_id=cid, source="karuna_gateway", type="email.inbound",
        object_refs=refs, status="CONSUMED",
        consumed_by_run_id=run.id,
        created_at=NOW - timedelta(days=age_days))
    db.add(signal)
    await db.flush()
    return uuid.UUID(str(signal.id)), uuid.UUID(str(run.id))


async def _record(cid: uuid.UUID, def_name: str, *, age_days: int) -> uuid.UUID:
    """A tenant record whose last touch is ``age_days`` old.

    ORM only. Textual SQL here would name a schema the translate map never
    rewrites — the STRAT T6 lesson, which `twin.materialise` records in its
    own docstring and which this fixture reproduced on the first run.
    """
    async with tenant_data_plane.session(cid) as ts:
        existing = (await ts.execute(
            select(TenantEntityDef.id).where(
                TenantEntityDef.company_id == cid,
                TenantEntityDef.name == def_name).limit(1))).first()
        if existing is None:
            new_def = TenantEntityDef(company_id=cid, name=def_name, fields=[])
            ts.add(new_def)
            await ts.flush()
            def_id = uuid.UUID(str(new_def.id))
        else:
            def_id = uuid.UUID(str(existing[0]))
        record = TenantRecord(
            company_id=cid, entity_def_id=def_id, data={"n": 1})
        ts.add(record)
        await ts.flush()
        rid = uuid.UUID(str(record.id))
        # updated_at carries an onupdate default, so the age is set by a
        # statement rather than by assigning to the instance.
        await ts.execute(
            update(TenantRecord)
            .where(TenantRecord.id == rid)
            .values(updated_at=NOW - timedelta(days=age_days)))
        await ts.commit()
    return rid


# ── the brief ───────────────────────────────────────────────────────────────

class TestBrief:
    async def test_a_board_build_is_a_brief_and_a_neighbour_is_not(self, tenants):
        """The scoping test and the kind test in one, because they are the
        two ways this endpoint could show the wrong brief."""
        mine, theirs = tenants
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            entity_id = await _colleague(db, mine, "Meta-Agent")
            run = ExecutionRun(
                company_id=mine, entity_id=entity_id, status="COMPLETED",
                started_at=NOW - timedelta(minutes=4), completed_at=NOW)
            db.add(run)
            await db.flush()
            db.add(PragyaDelegation(
                company_id=mine, kind="capability_build", status="done",
                promise="I'm having it built.",
                params={"subject": "chasing disputed invoices"},
                run_id=run.id, stage=6))
            # Same tenant, different kind — an assignment, not a hire.
            db.add(PragyaDelegation(
                company_id=mine, kind="research", status="done",
                promise="Let me read up on that.", params={"subject": "textiles"}))
            # Another tenant's brief, which must never appear.
            db.add(PragyaDelegation(
                company_id=theirs, kind="capability_build", status="promised",
                promise="theirs", params={"subject": "not yours"}))
            await db.commit()

        async with AsyncSessionLocal() as db:
            view = await brief_view(db, mine)

        assert len(view["briefs"]) == 1
        brief = view["briefs"][0]
        assert brief["subject"] == "chasing disputed invoices"
        assert brief["promise"] == "I'm having it built."
        assert brief["stage"] == 6
        assert brief["board_run"]["status"] == "COMPLETED"
        assert brief["board_run"]["completed_at"] is not None

    async def test_a_tenant_with_no_brief_is_told_what_is_missing(self, tenants):
        """The empty case is the one that matters: "no briefs yet" and "no
        store for a brief's terms" are different sentences, and the region
        must be able to tell them apart."""
        mine, _ = tenants
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            view = await brief_view(db, mine)
        assert view["briefs"] == []
        assert {a["field"] for a in view["absent"]} >= {
            "turns", "clauses", "may_touch", "district"}


# ── the exam ────────────────────────────────────────────────────────────────

class TestPastCases:
    async def test_a_case_names_its_record_its_colleague_and_its_approval(
        self, tenants,
    ):
        mine, _ = tenants
        from src.common.database import AsyncSessionLocal

        rid = await _record(mine, "Invoice", age_days=1)
        async with AsyncSessionLocal() as db:
            entity_id = await _colleague(db, mine, "Meera")
            _, run_id = await _handled(db, mine, entity_id, refs=[str(rid)])
            db.add(HumanApproval(
                run_id=run_id, checkpoint_trigger="record_write",
                checkpoint_key="collections.write", status="APPROVED",
                requested_at=NOW, responded_at=NOW))
            await db.commit()

        async with AsyncSessionLocal() as db:
            view = await past_cases_view(db, mine, now=NOW)

        assert len(view["cases"]) == 1
        case = view["cases"][0]
        assert case["signal_type"] == "email.inbound"
        assert case["records"][0]["def"] == "Invoice"
        assert case["records"][0]["label"] == f"Invoice {str(rid)[:8]}"
        assert case["outcome"]["handled_by"]["name"] == "Meera"
        assert case["outcome"]["approvals"][0]["checkpoint_key"] == "collections.write"
        assert case["outcome"]["approvals"][0]["status"] == "APPROVED"
        assert case["replayable"] is True
        assert case["blocked_because"] is None

    async def test_work_nobody_picked_up_is_not_a_case(self, tenants):
        """A signal with no consuming run has no ending to compare a
        candidate against."""
        mine, _ = tenants
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            db.add(Signal(
                company_id=mine, source="karuna_gateway", type="email.inbound",
                status="PENDING", created_at=NOW))
            await db.commit()

        async with AsyncSessionLocal() as db:
            view = await past_cases_view(db, mine, now=NOW)
        assert view["cases"] == []

    async def test_another_tenants_handled_work_is_not_visible(self, tenants):
        mine, theirs = tenants
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            entity_id = await _colleague(db, theirs, "Someone else")
            await _handled(db, theirs, entity_id)
            await db.commit()

        async with AsyncSessionLocal() as db:
            view = await past_cases_view(db, mine, now=NOW)
        assert view["cases"] == []

    async def test_a_case_older_than_the_window_reports_the_refusal(self, tenants):
        """The twin refuses a window longer than the cap, so a case beyond
        it cannot be put to any candidate — and the sentence says which
        rule refused, not that the case was uninteresting."""
        mine, _ = tenants
        from src.common.database import AsyncSessionLocal

        age = settings.TWIN_MAX_WINDOW_DAYS + 5
        async with AsyncSessionLocal() as db:
            entity_id = await _colleague(db, mine, "Meera")
            await _handled(db, mine, entity_id, age_days=age)
            await db.commit()

        async with AsyncSessionLocal() as db:
            view = await past_cases_view(db, mine, now=NOW)
        case = view["cases"][0]
        assert case["replayable"] is False
        assert str(settings.TWIN_MAX_WINDOW_DAYS) in case["blocked_because"]
        assert case["unknown_because"] is None

    async def test_a_record_untouched_since_before_the_cap_blocks_the_case(
        self, tenants,
    ):
        """Materialisation copies records by ``updated_at``, so a fresh
        signal over a stale record is still unreplayable — the thing the
        case turned on would not be in the glass room."""
        mine, _ = tenants
        from src.common.database import AsyncSessionLocal

        rid = await _record(
            mine, "Invoice", age_days=settings.TWIN_MAX_WINDOW_DAYS + 3)
        async with AsyncSessionLocal() as db:
            entity_id = await _colleague(db, mine, "Meera")
            await _handled(db, mine, entity_id, refs=[str(rid)])
            await db.commit()

        async with AsyncSessionLocal() as db:
            view = await past_cases_view(db, mine, now=NOW)
        case = view["cases"][0]
        assert case["replayable"] is False
        assert "glass room" in case["blocked_because"]

    async def test_a_ref_naming_no_record_leaves_the_answer_unknown(self, tenants):
        """Not False: a ref this company's records do not have is our blind
        spot, and reporting it as a refusal would make it look like a
        property of their history."""
        mine, _ = tenants
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            entity_id = await _colleague(db, mine, "Meera")
            await _handled(db, mine, entity_id, refs=[str(uuid.uuid4())])
            await db.commit()

        async with AsyncSessionLocal() as db:
            view = await past_cases_view(db, mine, now=NOW)
        case = view["cases"][0]
        assert case["replayable"] is None
        assert case["blocked_because"] is None
        assert case["unresolved_refs"]

    async def test_a_prefixed_ref_is_not_counted_as_a_missing_record(self, tenants):
        """``entity:…`` names something outside the record plane. Counting
        it as unresolvable would make every learning signal permanently
        unknown."""
        mine, _ = tenants
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            entity_id = await _colleague(db, mine, "Meera")
            await _handled(
                db, mine, entity_id, refs=[f"entity:{uuid.uuid4()}"])
            await db.commit()

        async with AsyncSessionLocal() as db:
            view = await past_cases_view(db, mine, now=NOW)
        case = view["cases"][0]
        assert case["replayable"] is True
        assert case["unresolved_refs"] == []
        assert case["other_refs"][0]["kind"] == "entity"
