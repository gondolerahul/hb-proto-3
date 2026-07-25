"""tenant_schema/data_plane.py — one codepath to reach a tenant's business DB.

The record service never knows *where* a tenant's data lives — it asks the
data plane for a session. Two backends, chosen by ``settings.TENANT_DB_BACKEND``:

* **schema** (dev/CI/test default) — a per-tenant Postgres *schema*
  (``t_<hex>``) on the control-plane database. Zero infra; the record service
  and every test run against it unchanged.
* **container** (prod) — a dedicated ``hb-tenant-db`` container per tenant,
  managed by :class:`TenantDatabaseManager` with tiered hibernation (§23.4).

Both create the same three ``TenantBase`` tables via the idempotent
``bootstrap`` and seed the HBS spine, so behaviour is identical.

**The twin plane (Inc-6 TWIN T1).** The Glasshouse needs an isolated copy of a
tenant's business data. It is a *sibling schema*, not a third backend: on the
schema backend the twin is ``t_<hex>_tw``; on the container backend it is a
named ``twin`` schema inside the tenant's own database. Both reach it through
the same ``schema_translate_map`` machinery they already use, so **the
two-backend design stays two backends** — which is what retired most of the
overview's TWIN risk row.

The isolation guarantee is the identifier itself. A session is built with one
translate map, so a twin session can only ever resolve ``tenant.*`` to the twin
schema and there is no session object that can see both planes. A write cannot
cross by accident because there is nothing to cross *through*.
"""
from __future__ import annotations

import enum
import logging
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "Plane", "TenantDataPlane", "tenant_data_plane", "schema_name_for",
    "get_tenant_session",
]

#: The schema a twin maps to on the container backend, where the live plane is
#: the database's own public schema and so has no name to suffix.
CONTAINER_TWIN_SCHEMA = "twin"


class Plane(str, enum.Enum):
    """Which copy of a tenant's business data a session addresses.

    ``LIVE`` is the real business. ``TWIN`` is the Glasshouse plane: same
    tables, same record service, same governance — writes that go nowhere.
    """

    LIVE = "live"
    TWIN = "twin"


def schema_name_for(
    company_id: uuid.UUID | str, plane: Plane = Plane.LIVE,
) -> str:
    """A safe Postgres identifier for a tenant's schema (hex only, no hyphens).

    Defaults to ``LIVE`` so every existing caller means what it always meant.
    """
    cid = company_id.hex if isinstance(company_id, uuid.UUID) else uuid.UUID(str(company_id)).hex
    return f"t_{cid}_tw" if plane is Plane.TWIN else f"t_{cid}"


class TenantDataPlane:
    """Vends sessions bound to a tenant's business database.

    Stateless enough to construct once (module singleton ``tenant_data_plane``);
    holds a bounded per-tenant engine cache for the container backend.
    """

    def __init__(self) -> None:
        self._backend = settings.TENANT_DB_BACKEND
        # company_id.hex → AsyncEngine (container backend only).
        self._engines: "OrderedDict[str, AsyncEngine]" = OrderedDict()
        self._ready: set[str] = set()

    @property
    def backend(self) -> str:
        return self._backend

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    async def ensure_ready(
        self, company_id: uuid.UUID, plane: Plane = Plane.LIVE,
    ) -> None:
        """Provision the tenant DB/schema, create tables, seed the HBS spine.

        Idempotent and cheap after the first call (memoised per process). The
        memo is keyed by *plane* as well as tenant — provisioning the live
        plane must not make the twin look ready, which would hand back a
        session pointed at a schema with no tables in it.
        """
        key = f"{company_id.hex}:{plane.value}"
        if key in self._ready:
            return
        if self._backend == "container":
            await self._ensure_container_ready(company_id, plane)
        else:
            await self._ensure_schema_ready(company_id, plane)
        self._ready.add(key)

    @asynccontextmanager
    async def session(
        self, company_id: uuid.UUID, plane: Plane = Plane.LIVE,
    ) -> AsyncIterator[AsyncSession]:
        """An AsyncSession scoped to the tenant's business DB (auto-ready).

        One session addresses exactly one plane. There is deliberately no way
        to ask for both: the translate map is fixed when the session is built,
        so a twin write has no path to the live schema (§4.1 of the TWIN
        design — the isolation guarantee is the identifier).
        """
        await self.ensure_ready(company_id, plane)
        if self._backend == "container":
            async with self._container_session(company_id, plane) as s:
                yield s
        else:
            async with self._schema_session(company_id, plane) as s:
                yield s

    def reset_cache(self) -> None:
        """Test hook — drop memoised readiness + engines."""
        self._ready.clear()
        self._engines.clear()

    # ------------------------------------------------------------------
    # schema backend (control-plane DB, per-tenant schema)
    # ------------------------------------------------------------------

    async def _ensure_schema_ready(
        self, company_id: uuid.UUID, plane: Plane = Plane.LIVE,
    ) -> None:
        from src.common.database import engine as control_engine

        schema = schema_name_for(company_id, plane)
        # CREATE SCHEMA on a plain connection; create tables through the
        # translate map so the symbolic "tenant" schema resolves to t_<hex>
        # (or t_<hex>_tw for the twin).
        async with control_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        async with control_engine.begin() as conn:
            tconn = await conn.execution_options(schema_translate_map={"tenant": schema})
            await self._create_tables(tconn)
            await self._sync_columns(conn, schema)
        await self._seed_if_empty(company_id, plane)

    @asynccontextmanager
    async def _schema_session(
        self, company_id: uuid.UUID, plane: Plane = Plane.LIVE,
    ) -> AsyncIterator[AsyncSession]:
        from src.common.database import engine as control_engine

        schema = schema_name_for(company_id, plane)
        # schema_translate_map qualifies "tenant.<table>" → "t_<hex>.<table>"
        # per session — leak-free (no connection-level SET search_path).
        engine = control_engine.execution_options(schema_translate_map={"tenant": schema})
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session

    # ------------------------------------------------------------------
    # container backend (prod — dedicated hb-tenant-db per tenant)
    # ------------------------------------------------------------------

    @staticmethod
    def _container_schema(plane: Plane) -> str | None:
        """Where ``tenant.*`` resolves inside a tenant's dedicated database.

        ``None`` (the live plane) means the database's own default schema — it
        has no name to suffix, which is why the twin needs one of its own here
        rather than the ``_tw`` suffix the schema backend uses.
        """
        return CONTAINER_TWIN_SCHEMA if plane is Plane.TWIN else None

    async def _ensure_container_ready(
        self, company_id: uuid.UUID, plane: Plane = Plane.LIVE,
    ) -> None:
        engine = await self._container_engine(company_id)
        schema = self._container_schema(plane)
        if schema is not None:
            async with engine.begin() as conn:
                await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        # Dedicated DB: the symbolic "tenant" schema maps to the default public
        # for the live plane, and to the named twin schema for the twin.
        async with engine.begin() as conn:
            tconn = await conn.execution_options(schema_translate_map={"tenant": schema})
            await self._create_tables(tconn)
            await self._sync_columns(conn, schema)
        await self._seed_if_empty(company_id, plane)

    @asynccontextmanager
    async def _container_session(
        self, company_id: uuid.UUID, plane: Plane = Plane.LIVE,
    ) -> AsyncIterator[AsyncSession]:
        base = await self._container_engine(company_id)
        engine = base.execution_options(
            schema_translate_map={"tenant": self._container_schema(plane)})
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session

    async def _container_engine(self, company_id: uuid.UUID) -> AsyncEngine:
        from sqlalchemy.ext.asyncio import create_async_engine

        from src.ai.tools.sandbox.tenant_db_manager import TenantDatabaseManager

        key = company_id.hex
        cached = self._engines.get(key)
        if cached is not None:
            self._engines.move_to_end(key)
            return cached

        manager = TenantDatabaseManager()
        url = await manager.ensure(str(company_id))  # lazy-wakes/creates the container
        engine = create_async_engine(url, pool_size=4, max_overflow=8, pool_pre_ping=True)
        self._engines[key] = engine
        # Evict the least-recently-used engine past the cache bound.
        while len(self._engines) > settings.TENANT_DB_ENGINE_CACHE_SIZE:
            _old_key, old_engine = self._engines.popitem(last=False)
            await old_engine.dispose()
        return engine

    # ------------------------------------------------------------------
    # shared: table creation + HBS seed
    # ------------------------------------------------------------------

    @staticmethod
    async def _create_tables(conn: Any) -> None:
        from src.ai.tenant_schema.models import TenantBase

        await conn.run_sync(TenantBase.metadata.create_all)

    @staticmethod
    async def _sync_columns(conn: Any, schema: str | None) -> None:
        """Additively evolve an *existing* tenant schema (§10.2 additive rule).

        ``create_all`` creates missing tables but never alters an existing one,
        so a column added to a tenant model after Inc-1's provisioning would be
        absent on already-provisioned tenants. These idempotent
        ``ADD COLUMN IF NOT EXISTS`` statements converge new and existing
        schemas; new columns append to the list, never a destructive change.
        """
        prefix = f'"{schema}".' if schema else ""
        # Inc-4 CONN+SOR: the mirror columns on tenant_records (§21.2).
        for col in ("sor", "external_ref"):
            await conn.execute(text(
                f'ALTER TABLE {prefix}"tenant_records" ADD COLUMN IF NOT EXISTS "{col}" JSONB'
            ))
        # One mirror per external object (§21.2 dedupe). company_id is constant
        # within a tenant schema, so (entity_def_id, external_id) is sufficient.
        await conn.execute(text(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_tenant_records_external" '
            f"ON {prefix}\"tenant_records\" (entity_def_id, (external_ref->>'external_id')) "
            f"WHERE external_ref IS NOT NULL"
        ))

    async def _seed_if_empty(
        self, company_id: uuid.UUID, plane: Plane = Plane.LIVE,
    ) -> None:
        from src.ai.tenant_schema.bootstrap import seed_hbs_spine

        async with (
            self._container_session(company_id, plane)
            if self._backend == "container"
            else self._schema_session(company_id, plane)
        ) as session:
            await seed_hbs_spine(session, company_id)
            await session.commit()

    # ------------------------------------------------------------------
    # twin lifecycle
    # ------------------------------------------------------------------

    async def drop_twin(self, company_id: uuid.UUID) -> None:
        """Reap a tenant's twin plane (TWIN §4.3 — per-run, not persistent).

        A permanent shadow of every tenant would double the storage bill of a
        feature most tenants use occasionally. Dropping the whole schema rather
        than truncating tables keeps this honest about the *definitions* too: a
        scenario that varied the schema must not leave that variation behind
        for the next run to inherit.

        Refuses to touch anything but a twin, by construction — it can only
        name a schema `schema_name_for(..., TWIN)` produced.
        """
        schema = schema_name_for(company_id, Plane.TWIN)
        if not schema.endswith("_tw"):  # pragma: no cover — defensive
            raise ValueError(f"refusing to drop non-twin schema {schema!r}")

        if self._backend == "container":
            engine = await self._container_engine(company_id)
            target = CONTAINER_TWIN_SCHEMA
        else:
            from src.common.database import engine as control_engine

            engine = control_engine
            target = schema

        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{target}" CASCADE'))
        self._ready.discard(f"{company_id.hex}:{Plane.TWIN.value}")
        logger.info("Reaped twin plane for company %s", company_id)


# Module singleton — reuse across the app.
tenant_data_plane = TenantDataPlane()


@asynccontextmanager
async def get_tenant_session(
    company_id: uuid.UUID, plane: Plane = Plane.LIVE,
) -> AsyncIterator[AsyncSession]:
    """Convenience wrapper over the module-singleton data plane."""
    async with tenant_data_plane.session(company_id, plane) as session:
        yield session
