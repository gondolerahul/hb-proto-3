"""Inc 6 / TWIN T2 + T3 + T8 — materialisation, the shelf, and the cap. ``needs_db``.

Materialisation is where §4.2's "bounded, not a copy of everything" either
holds or does not, so most of this file is about what is *left behind*: records
outside the window, objects outside the scope, and — the expensive one —
documents and embeddings, which the twin reads from the control plane and must
never copy.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from src.ai.tenant_schema.data_plane import Plane, schema_name_for, tenant_data_plane
from src.ai.tenant_schema.models import TenantEntityDef, TenantRecord
from src.ai.twin.materialise import Scope, ScopeRefused, estimate_rows, materialise, reap

# SQLAlchemy resolves a ForeignKey by table *name* at mapper-configuration
# time, so every table `twin.models` points at has to be imported before the
# twin mappers are first used. In the running app `main.py` imports all of
# these long before anything touches a twin model; a test that imports
# `twin.models` in isolation does not, and fails with NoReferencedTableError
# rather than anything to do with what it was testing.
import src.auth.models  # noqa: F401  — companies, users
import src.ai.evolution.models  # noqa: F401  — entity_versions

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def seeded():
    """A tenant with records of two objects, some inside the window, some not."""
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
            {"id": str(cid), "n": f"twinmat-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid, Plane.LIVE)

    async with tenant_data_plane.session(cid, Plane.LIVE) as s:
        defs = (await s.execute(
            select(TenantEntityDef).order_by(TenantEntityDef.name).limit(2))).scalars().all()
        first, second = defs[0], defs[1]
        recent = datetime.utcnow() - timedelta(days=2)
        old = datetime.utcnow() - timedelta(days=90)
        s.add_all([
            TenantRecord(company_id=cid, entity_def_id=first.id,
                         data={"name": "in-window"}, updated_at=recent),
            TenantRecord(company_id=cid, entity_def_id=first.id,
                         data={"name": "out-of-window"}, updated_at=old),
            TenantRecord(company_id=cid, entity_def_id=second.id,
                         data={"name": "other-object"}, updated_at=recent),
        ])
        await s.commit()

    try:
        yield {"company": cid, "in_scope": first.name, "out_of_scope": second.name}
    finally:
        from src.common.database import engine as control_engine
        async with control_engine.begin() as conn:
            for plane in (Plane.LIVE, Plane.TWIN):
                await conn.execute(text(
                    f'DROP SCHEMA IF EXISTS "{schema_name_for(cid, plane)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            for tbl in ("twin_runs", "twin_scenarios"):
                await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"),
                                {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def _twin_names(company_id: uuid.UUID) -> set[str]:
    async with tenant_data_plane.session(company_id, Plane.TWIN) as s:
        rows = (await s.execute(select(TenantRecord.data))).scalars().all()
    return {(r or {}).get("name") for r in rows}


class TestBoundedCopy:
    async def test_the_schema_is_always_copied(self, seeded):
        """§4.2: `tenant_entity_defs` always, because it is small and because
        everything else references it."""
        result = await materialise(seeded["company"], Scope(objects=(), window_days=7))
        assert result.entity_defs > 0
        assert result.records == 0

    async def test_entity_def_ids_are_preserved(self, seeded):
        """Record FKs must resolve, and a scenario comparing against the live
        business has to be talking about the same object definitions."""
        await materialise(seeded["company"],
                          Scope(objects=(seeded["in_scope"],), window_days=7))
        async with tenant_data_plane.session(seeded["company"], Plane.LIVE) as s:
            live_ids = set((await s.execute(select(TenantEntityDef.id))).scalars().all())
        async with tenant_data_plane.session(seeded["company"], Plane.TWIN) as s:
            twin_ids = set((await s.execute(select(TenantEntityDef.id))).scalars().all())
        assert live_ids == twin_ids

    async def test_only_objects_in_scope_are_copied(self, seeded):
        await materialise(seeded["company"],
                          Scope(objects=(seeded["in_scope"],), window_days=7))
        names = await _twin_names(seeded["company"])
        assert "in-window" in names
        assert "other-object" not in names

    async def test_only_records_in_the_window_are_copied(self, seeded):
        """The window is the point: copying a tenant's whole business per
        what-if is exactly the expense decision 7 makes visible."""
        await materialise(seeded["company"],
                          Scope(objects=(seeded["in_scope"],), window_days=7))
        names = await _twin_names(seeded["company"])
        assert "in-window" in names
        assert "out-of-window" not in names

    async def test_a_wider_window_reaches_further_back(self, seeded):
        await materialise(seeded["company"],
                          Scope(objects=(seeded["in_scope"],), window_days=30))
        assert "out-of-window" not in await _twin_names(seeded["company"])
        # 90 days is outside even the cap, which is the point of the cap.
        with pytest.raises(ScopeRefused):
            await materialise(seeded["company"],
                              Scope(objects=(seeded["in_scope"],), window_days=90))

    async def test_documents_and_embeddings_are_never_copied(self, seeded):
        """§4.2's "never". Re-embedding a tenant's library for a what-if would
        be the single most expensive thing the Glasshouse could do, and it
        would buy nothing — retrieval is not what the scenario is varying."""
        from src.common.database import engine

        await materialise(seeded["company"],
                          Scope(objects=(seeded["in_scope"],), window_days=7))
        twin_schema = schema_name_for(seeded["company"], Plane.TWIN)
        async with engine.connect() as conn:
            tables = set((await conn.execute(
                text("SELECT table_name FROM information_schema.tables "
                     "WHERE table_schema = :s"), {"s": twin_schema})).scalars().all())
        assert "documents" not in tables
        assert "document_chunks" not in tables


class TestIdempotence:
    async def test_rematerialising_replaces_rather_than_doubles(self, seeded):
        scope = Scope(objects=(seeded["in_scope"],), window_days=7)
        first = await materialise(seeded["company"], scope)
        second = await materialise(seeded["company"], scope)
        assert first.records == second.records

        async with tenant_data_plane.session(seeded["company"], Plane.TWIN) as s:
            total = (await s.execute(
                select(func.count()).select_from(TenantRecord))).scalar()
        assert total == second.records

    async def test_the_live_plane_is_never_written(self, seeded):
        """Materialisation reads live and writes twin. It must not be capable
        of the reverse."""
        async with tenant_data_plane.session(seeded["company"], Plane.LIVE) as s:
            before = (await s.execute(
                select(func.count()).select_from(TenantRecord))).scalar()
        await materialise(seeded["company"],
                          Scope(objects=(seeded["in_scope"],), window_days=7))
        async with tenant_data_plane.session(seeded["company"], Plane.LIVE) as s:
            after = (await s.execute(
                select(func.count()).select_from(TenantRecord))).scalar()
        assert before == after


class TestEstimate:
    async def test_the_estimate_matches_what_gets_copied(self, seeded):
        """§6.4 — a tenant should never learn a what-if's price afterwards, so
        the estimate has to be about the same rows the run copies."""
        scope = Scope(objects=(seeded["in_scope"],), window_days=7)
        predicted = await estimate_rows(seeded["company"], scope)
        actual = await materialise(seeded["company"], scope)
        assert predicted == actual.records

    async def test_an_empty_scope_estimates_nothing(self, seeded):
        assert await estimate_rows(seeded["company"], Scope(objects=())) == 0

    async def test_estimating_copies_nothing(self, seeded):
        """A price check must not itself cost anything."""
        await tenant_data_plane.ensure_ready(seeded["company"], Plane.TWIN)
        await estimate_rows(seeded["company"],
                            Scope(objects=(seeded["in_scope"],), window_days=7))
        async with tenant_data_plane.session(seeded["company"], Plane.TWIN) as s:
            total = (await s.execute(
                select(func.count()).select_from(TenantRecord))).scalar()
        assert total == 0


class TestReaping:
    async def test_reap_empties_the_glass_room(self, seeded):
        await materialise(seeded["company"],
                          Scope(objects=(seeded["in_scope"],), window_days=7))
        assert await _twin_names(seeded["company"]) != set()
        await reap(seeded["company"])
        assert await _twin_names(seeded["company"]) == set()


class TestShelfAndCap:
    async def test_a_scenario_and_its_runs_persist(self, seeded):
        from src.ai.twin.models import ScenarioKind, TwinRun, TwinScenario
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            scenario = TwinScenario(
                company_id=seeded["company"], name="chase harder",
                kind=ScenarioKind.POLICY,
                scope={"objects": [seeded["in_scope"]], "window_days": 7})
            db.add(scenario)
            await db.flush()
            db.add(TwinRun(company_id=seeded["company"], scenario_id=scenario.id,
                           grade="replay", method="replayed 3 signals",
                           metrics={"revenue": 120}, cost_usd=0.02))
            await db.commit()
            scenario_id = scenario.id

        async with AsyncSessionLocal() as db:
            runs = (await db.execute(
                select(TwinRun).where(TwinRun.scenario_id == scenario_id))).scalars().all()
        assert len(runs) == 1
        assert runs[0].grade == "replay"

    async def test_a_baseline_run_needs_no_scenario(self, seeded):
        """Nullable `scenario_id` is what lets every scenario reuse one
        baseline (§6.2) — that is the whole saving."""
        from src.ai.twin.models import TwinRun
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            db.add(TwinRun(company_id=seeded["company"], scenario_id=None,
                           grade="replay", is_baseline=True, cost_usd=0.05))
            await db.commit()

        async with AsyncSessionLocal() as db:
            found = (await db.execute(
                select(TwinRun).where(TwinRun.company_id == seeded["company"],
                                      TwinRun.is_baseline.is_(True)))).scalars().all()
        assert len(found) == 1

    async def test_the_daily_cap_parks_rather_than_fails(self, seeded):
        """§6.6 — "resumes tomorrow" is a budget a tenant understands, where
        "twin run failed" is a bug report."""
        from src.ai.twin.cost import admit, spent_today
        from src.ai.twin.models import TwinRun
        from src.common.config import settings
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            db.add(TwinRun(company_id=seeded["company"], grade="replay",
                           cost_usd=settings.TWIN_DAILY_CAP_USD))
            await db.commit()

        async with AsyncSessionLocal() as db:
            assert await spent_today(db, seeded["company"]) == pytest.approx(
                settings.TWIN_DAILY_CAP_USD)
            decision = await admit(db, seeded["company"], 1.0)

        assert decision.admitted is False
        assert decision.parked is True
        assert "resumes tomorrow" in decision.reason

    async def test_a_run_inside_the_cap_is_admitted(self, seeded):
        from src.ai.twin.cost import admit
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            decision = await admit(db, seeded["company"], 0.01)
        assert decision.admitted is True

    async def test_twin_spend_is_tenant_initiated(self):
        """Charter decision 7, overriding ratified spec §12.1. Putting twin
        spend in the platform class would let tenant experimentation exhaust
        the cap that exists to protect tenants *from* platform work (B13)."""
        from src.ai.services.cost_attribution import (
            PLATFORM_INITIATED_ATTRIBUTIONS,
            CostAttribution,
        )

        assert CostAttribution.TWIN_RUN.value not in PLATFORM_INITIATED_ATTRIBUTIONS
