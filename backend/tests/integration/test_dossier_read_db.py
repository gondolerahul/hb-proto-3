"""Inc-7 D8 E3 — the colleague dossier against real rows. ``needs_db``.

The projection's rules are unit-tested next door. What needs a database is
what the pure tests cannot reach: that the read is company-scoped at every
hop (including the walk up the tree that finds the district), that the
reliability readings come from this colleague's runs over the sweep's own
window and nobody else's, and that the checkpoint copy comes from the seeded
registry rather than from anything this module made up.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.dossier.read import dossier_view
from src.ai.governance.demotion_sweep import WINDOW_DAYS

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


async def _make_company(name: str) -> uuid.UUID:
    from src.common.database import AsyncSessionLocal

    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"{name}-{cid.hex[:8]}"})
        await s.commit()
    return cid


async def _drop_company(cid: uuid.UUID) -> None:
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        await s.execute(
            text("DELETE FROM human_approvals WHERE run_id IN "
                 "(SELECT id FROM execution_runs WHERE company_id = :c)"),
            {"c": str(cid)})
        await s.execute(
            text("DELETE FROM execution_runs WHERE company_id = :c"), {"c": str(cid)})
        await s.execute(
            text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
            {"c": str(cid)})
        await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
        await s.commit()


async def _seed_colleague(company: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """A district (PROCESS) and one colleague (AGENT) under it — the shape the
    Solo Pack seeds, because that is the shape the dossier has to read."""
    from src.ai.orm.entity import HierarchicalEntity
    from src.common.database import AsyncSessionLocal

    process_id, agent_id = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as s:
        s.add(HierarchicalEntity(
            id=process_id, company_id=company, type="PROCESS", status="ACTIVE",
            name="p08-order-to-cash", display_name="Order-to-Cash",
            metadata_extensions={"process_code": "P08"}))
        s.add(HierarchicalEntity(
            id=agent_id, company_id=company, parent_id=process_id,
            type="AGENT", status="ACTIVE",
            name="agt-038-accounts-receivable", display_name="Accounts Receivable",
            description="Chases overdue invoices and applies received payments.",
            goal="Draft collection reminders and record payments.",
            identity={"role": "Accounts Receivable",
                      "system_prompt": "You manage receivables.",
                      "personality": {"tone": "professional"}},
            capabilities={"tools": [{"tool_id": "issue_refund"},
                                    {"tool_id": "emit_business_signal"}]},
            governance={"autonomy_level": "A1", "sod_class": "maker",
                        "max_cost_usd": 0.5, "timeout_ms": 60000,
                        "authority": {"refund_usd": 200}}))
        await s.commit()
    return process_id, agent_id


async def _seed_runs(company: uuid.UUID, entity_id: uuid.UUID) -> None:
    """Three runs inside the window (one failed) and one long outside it.

    The stale run is the point: a reliability reading that silently included
    it would not be the reading the demotion sweep judges on.
    """
    from src.ai.orm.execution import ExecutionRun
    from src.common.database import AsyncSessionLocal

    now = datetime.utcnow()
    async with AsyncSessionLocal() as s:
        for status, age_days, ms in (
            ("COMPLETED", 1, 1000), ("COMPLETED", 2, 2000),
            ("FAILED", 3, 3000), ("FAILED", WINDOW_DAYS + 5, 4000),
        ):
            s.add(ExecutionRun(
                id=uuid.uuid4(), company_id=company, entity_id=entity_id,
                status=status, execution_time_ms=ms,
                created_at=now - timedelta(days=age_days)))
        await s.commit()


@pytest_asyncio.fixture
async def tenants():
    """Two tenants, because the interesting failure of a read model is
    reading someone else's rows, not reading none."""
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import engine

    await engine.dispose()
    mine = await _make_company("dossier")
    theirs = await _make_company("dossier-other")
    try:
        yield mine, theirs
    finally:
        await _drop_company(mine)
        await _drop_company(theirs)


async def test_the_dossier_reads_the_colleagues_own_terms(tenants):
    from src.common.database import AsyncSessionLocal

    mine, _ = tenants
    _, agent_id = await _seed_colleague(mine)
    async with AsyncSessionLocal() as db:
        view = await dossier_view(db, mine, agent_id)

    assert view is not None
    assert view["display_name"] == "Accounts Receivable"
    assert view["role"] == "Accounts Receivable"
    assert view["district"] == {
        "process_code": "P08", "name": "Order-to-Cash", "quarter": "finance"}
    assert view["autonomy"]["band"] == "A1"
    # Never demoted is an absent stamp, not an empty one.
    assert "demoted_at" not in view["autonomy"]

    labels = {c["label"] for c in view["charter"]["clauses"]}
    assert labels == {"Goal", "Brief", "Role", "Instructions", "Tone",
                      "Segregation of duties", "Cost ceiling per run"}
    # The governance record is the same charter, verbatim — the surface offers
    # both renderings as one flip, so they cannot come from two sources.
    assert view["charter"]["governance"]["authority"] == {"refund_usd": 200}


async def test_the_authority_block_carries_the_seeded_checkpoint_copy(tenants):
    """The description, SLA and mandatory flag come from
    ``hitl_checkpoint_defs`` — the registry the gate raises against."""
    from src.common.database import AsyncSessionLocal

    mine, _ = tenants
    _, agent_id = await _seed_colleague(mine)
    async with AsyncSessionLocal() as db:
        view = await dossier_view(db, mine, agent_id)
        seeded = (await db.execute(
            text("SELECT description, sla_seconds, platform_mandatory "
                 "FROM hitl_checkpoint_defs WHERE key = 'before_refund_above_band'")
        )).one()

    assert view is not None
    refund = [a for a in view["charter"]["authority"] if a["category"] == "refund"]
    assert len(refund) == 1
    assert refund[0]["tools"] == ["issue_refund"]
    assert refund[0]["decision"] == "RAISE_HITL"      # A1 — a human sees every one
    assert refund[0]["checkpoint_description"] == seeded[0]
    assert refund[0]["sla_seconds"] == seeded[1]
    assert refund[0]["platform_mandatory"] is seeded[2]


async def test_reliability_counts_this_colleague_inside_the_sweeps_window(tenants):
    from src.common.database import AsyncSessionLocal

    mine, _ = tenants
    _, agent_id = await _seed_colleague(mine)
    await _seed_runs(mine, agent_id)
    async with AsyncSessionLocal() as db:
        view = await dossier_view(db, mine, agent_id)

    assert view is not None
    reliability = view["reliability"]
    assert reliability["runs_total"] == 3          # the stale one is outside
    assert reliability["runs_failed"] == 1
    assert reliability["failure_rate"] == pytest.approx(1 / 3)
    assert reliability["p95_latency_ms"] is not None
    assert reliability["demotion_bar"]["latency_floor_ms"] == 60000.0


async def test_another_tenants_colleague_does_not_exist_here(tenants):
    """Both directions: the id is real, and it reads as missing from the
    other tenant's session — which is the same answer an invented id gets."""
    from src.common.database import AsyncSessionLocal

    mine, theirs = tenants
    _, agent_id = await _seed_colleague(mine)
    async with AsyncSessionLocal() as db:
        assert await dossier_view(db, mine, agent_id) is not None
        assert await dossier_view(db, theirs, agent_id) is None
        assert await dossier_view(db, mine, uuid.uuid4()) is None


async def test_the_district_walk_cannot_leave_the_tenant(tenants):
    """The parent pointer is a column. A colleague whose parent belongs to
    another company must report no district rather than climb into it."""
    from src.ai.orm.entity import HierarchicalEntity
    from src.common.database import AsyncSessionLocal

    mine, theirs = tenants
    their_process_id, _ = await _seed_colleague(theirs)
    orphan_id = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        s.add(HierarchicalEntity(
            id=orphan_id, company_id=mine, parent_id=their_process_id,
            type="AGENT", status="ACTIVE", name="agt-999-stray"))
        await s.commit()

    async with AsyncSessionLocal() as db:
        view = await dossier_view(db, mine, orphan_id)

    assert view is not None
    assert view["district"] is None


async def test_the_absences_travel_with_the_payload(tenants):
    """The surface must be told what the platform cannot answer, or it will
    find an empty field and fill it in."""
    from src.common.database import AsyncSessionLocal

    mine, _ = tenants
    _, agent_id = await _seed_colleague(mine)
    async with AsyncSessionLocal() as db:
        view = await dossier_view(db, mine, agent_id)

    assert view is not None
    fields = {item["field"] for item in view["absent"]}
    assert {"slos", "probation", "standing"} <= fields
    assert "slos" not in view and "probation" not in view and "standing" not in view
