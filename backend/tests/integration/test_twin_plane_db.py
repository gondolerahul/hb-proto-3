"""Inc 6 / TWIN T1 — the twin plane is a sibling schema, and it is isolated. ``needs_db``.

T1 comes before everything else in TWIN because if the sibling-schema approach
does not hold, every later task changes shape. What it has to hold is one
claim, made in the design (§4.1) and tested here: **a twin session can only
ever resolve `tenant.*` to the twin schema**, so a write cannot cross into the
live business by accident. There is no session object that can see both.

Everything addresses the tenant tables through the **ORM models**, never
through `text()`. That is not a style preference — `schema_translate_map`
rewrites SQLAlchemy constructs and does *not* touch textual SQL, so a raw
`SELECT ... FROM tenant.tenant_records` resolves against a literal schema
called "tenant" and fails. Any future code reaching the tenant plane has the
same constraint.

The record service is driven through both planes on purpose. Proving the
*plumbing* is isolated is not the same as proving the thing that will actually
write is isolated, and only the second is the guarantee anyone cares about.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from src.ai.tenant_schema.data_plane import Plane, schema_name_for, tenant_data_plane
from src.ai.tenant_schema.models import TenantEntityDef, TenantRecord

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
            {"id": str(cid), "n": f"twin-test-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    try:
        yield cid
    finally:
        async with engine.begin() as conn:
            for plane in (Plane.LIVE, Plane.TWIN):
                await conn.execute(text(
                    f'DROP SCHEMA IF EXISTS "{schema_name_for(cid, plane)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def _write_marker(tenant_id: uuid.UUID, plane: Plane, marker: str) -> None:
    async with tenant_data_plane.session(tenant_id, plane) as s:
        definition = (await s.execute(select(TenantEntityDef).limit(1))).scalar_one()
        s.add(TenantRecord(
            company_id=tenant_id, entity_def_id=definition.id, data={"marker": marker}))
        await s.commit()


async def _count_marker(tenant_id: uuid.UUID, plane: Plane, marker: str) -> int:
    async with tenant_data_plane.session(tenant_id, plane) as s:
        result = (await s.execute(
            select(func.count()).select_from(TenantRecord).where(
                TenantRecord.data["marker"].astext == marker))).scalar()
    return int(result or 0)


class TestNaming:
    def test_the_twin_is_a_sibling_of_the_live_schema(self):
        cid = uuid.uuid4()
        assert schema_name_for(cid, Plane.TWIN) == schema_name_for(cid) + "_tw"

    def test_live_is_the_default_so_every_existing_caller_is_unchanged(self):
        cid = uuid.uuid4()
        assert schema_name_for(cid) == schema_name_for(cid, Plane.LIVE)
        assert not schema_name_for(cid).endswith("_tw")

    def test_two_tenants_never_share_a_twin(self):
        assert schema_name_for(uuid.uuid4(), Plane.TWIN) != schema_name_for(
            uuid.uuid4(), Plane.TWIN)


class TestBootstrap:
    async def test_both_planes_bootstrap_the_same_tables(self, tenant):
        """Same `TenantBase`, same bootstrap, same HBS spine — the twin is a
        copy of the *shape*, which is what lets the record service run on it
        without knowing which plane it is on."""
        from src.common.database import engine

        await tenant_data_plane.ensure_ready(tenant, Plane.LIVE)
        await tenant_data_plane.ensure_ready(tenant, Plane.TWIN)

        tables = {}
        async with engine.connect() as conn:
            for plane in (Plane.LIVE, Plane.TWIN):
                rows = (await conn.execute(
                    text("SELECT table_name FROM information_schema.tables "
                         "WHERE table_schema = :s"),
                    {"s": schema_name_for(tenant, plane)})).scalars().all()
                tables[plane] = set(rows)

        assert tables[Plane.LIVE], "the live plane should have tables"
        assert tables[Plane.LIVE] == tables[Plane.TWIN]

    async def test_readiness_is_memoised_per_plane(self, tenant):
        """Provisioning the live plane must not make the twin *look* ready —
        that would hand back a session pointed at a schema with no tables."""
        from src.common.database import engine

        await tenant_data_plane.ensure_ready(tenant, Plane.LIVE)
        async with engine.connect() as conn:
            exists = (await conn.execute(
                text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
                {"s": schema_name_for(tenant, Plane.TWIN)})).first()
        assert exists is None, "the twin should not be created by readying live"

        await tenant_data_plane.ensure_ready(tenant, Plane.TWIN)
        async with engine.connect() as conn:
            exists = (await conn.execute(
                text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
                {"s": schema_name_for(tenant, Plane.TWIN)})).first()
        assert exists is not None

    async def test_the_twin_seeds_its_own_hbs_spine(self, tenant):
        """§4.2: the schema itself and the spine are always materialised,
        because they are small and everything else depends on them."""
        async with tenant_data_plane.session(tenant, Plane.TWIN) as s:
            count = (await s.execute(
                select(func.count()).select_from(TenantEntityDef))).scalar()
        assert count and count > 0


class TestIsolation:
    """The guarantee. A twin write must have no path to the live business."""

    async def test_a_twin_write_is_invisible_to_the_live_plane(self, tenant):
        await _write_marker(tenant, Plane.TWIN, "twin-only")
        assert await _count_marker(tenant, Plane.TWIN, "twin-only") == 1
        assert await _count_marker(tenant, Plane.LIVE, "twin-only") == 0, (
            "a twin write reached the live plane")

    async def test_a_live_write_is_invisible_to_the_twin(self, tenant):
        """The other direction. A materialisation copies deliberately (T2);
        the planes must not share rows by accident before then."""
        await _write_marker(tenant, Plane.LIVE, "live-only")
        assert await _count_marker(tenant, Plane.LIVE, "live-only") == 1
        assert await _count_marker(tenant, Plane.TWIN, "live-only") == 0

    async def test_a_twin_session_never_resolves_to_the_live_schema(self, tenant):
        """Stated as the design states it: the isolation guarantee is the
        identifier. A session carries exactly one mapping for `tenant`, fixed
        when it was built, and there is no API that gives it a second."""
        async with tenant_data_plane.session(tenant, Plane.TWIN) as s:
            resolved = s.get_bind().get_execution_options().get(
                "schema_translate_map", {})
        assert resolved.get("tenant") == schema_name_for(tenant, Plane.TWIN)
        assert schema_name_for(tenant, Plane.LIVE) not in resolved.values()

    async def test_the_record_service_writes_only_where_it_was_handed(self, tenant):
        """Proving the plumbing is isolated is not the same as proving the
        thing that actually writes is. This drives the real record service."""
        from src.ai.tenant_schema.record_service import RecordService

        async def count_named(plane: Plane) -> int:
            async with tenant_data_plane.session(tenant, plane) as s:
                result = (await s.execute(
                    select(func.count()).select_from(TenantRecord).where(
                        TenantRecord.data["name"].astext == "glasshouse-only"))).scalar()
            return int(result or 0)

        async with tenant_data_plane.session(tenant, Plane.TWIN) as s:
            definition = (await s.execute(
                select(TenantEntityDef).order_by(TenantEntityDef.name).limit(1)
            )).scalar_one()
            # `name` rather than an invented key: the record service validates
            # against the def's own fields, which is itself worth exercising —
            # the twin runs the *real* service, not a permissive stand-in.
            await RecordService(s, tenant).create(
                definition.name, {"name": "glasshouse-only"}, force_cross_owner=True)
            await s.commit()

        assert await count_named(Plane.TWIN) == 1
        assert await count_named(Plane.LIVE) == 0, (
            "the record service wrote across planes")


class TestReaping:
    async def test_dropping_the_twin_leaves_the_live_plane_alone(self, tenant):
        """§4.3 — the twin is per-run and reaped. The live business is not."""
        from src.common.database import engine

        await tenant_data_plane.ensure_ready(tenant, Plane.LIVE)
        await tenant_data_plane.ensure_ready(tenant, Plane.TWIN)
        await tenant_data_plane.drop_twin(tenant)

        async with engine.connect() as conn:
            twin = (await conn.execute(
                text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
                {"s": schema_name_for(tenant, Plane.TWIN)})).first()
            live = (await conn.execute(
                text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
                {"s": schema_name_for(tenant, Plane.LIVE)})).first()
        assert twin is None
        assert live is not None

    async def test_a_reaped_twin_can_be_rebuilt(self, tenant):
        """The memo has to be cleared by the drop, or the next scenario gets a
        session pointed at a schema that no longer exists."""
        await tenant_data_plane.ensure_ready(tenant, Plane.TWIN)
        await tenant_data_plane.drop_twin(tenant)

        async with tenant_data_plane.session(tenant, Plane.TWIN) as s:
            count = (await s.execute(
                select(func.count()).select_from(TenantEntityDef))).scalar()
        assert count and count > 0

    async def test_a_reaped_twin_carries_nothing_over(self, tenant):
        """Dropping the schema rather than truncating is what makes this true
        for the *definitions* too: a scenario that varied the schema must not
        leave that variation behind for the next run to inherit."""
        await _write_marker(tenant, Plane.TWIN, "previous-run")
        assert await _count_marker(tenant, Plane.TWIN, "previous-run") == 1

        await tenant_data_plane.drop_twin(tenant)
        assert await _count_marker(tenant, Plane.TWIN, "previous-run") == 0
