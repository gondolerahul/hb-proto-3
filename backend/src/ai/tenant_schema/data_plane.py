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
"""
from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = ["TenantDataPlane", "tenant_data_plane", "schema_name_for", "get_tenant_session"]


def schema_name_for(company_id: uuid.UUID | str) -> str:
    """A safe Postgres identifier for a tenant's schema (hex only, no hyphens)."""
    cid = company_id.hex if isinstance(company_id, uuid.UUID) else uuid.UUID(str(company_id)).hex
    return f"t_{cid}"


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

    async def ensure_ready(self, company_id: uuid.UUID) -> None:
        """Provision the tenant DB/schema, create tables, seed the HBS spine.

        Idempotent and cheap after the first call (memoised per process).
        """
        key = company_id.hex
        if key in self._ready:
            return
        if self._backend == "container":
            await self._ensure_container_ready(company_id)
        else:
            await self._ensure_schema_ready(company_id)
        self._ready.add(key)

    @asynccontextmanager
    async def session(self, company_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
        """An AsyncSession scoped to the tenant's business DB (auto-ready)."""
        await self.ensure_ready(company_id)
        if self._backend == "container":
            async with self._container_session(company_id) as s:
                yield s
        else:
            async with self._schema_session(company_id) as s:
                yield s

    def reset_cache(self) -> None:
        """Test hook — drop memoised readiness + engines."""
        self._ready.clear()
        self._engines.clear()

    # ------------------------------------------------------------------
    # schema backend (control-plane DB, per-tenant schema)
    # ------------------------------------------------------------------

    async def _ensure_schema_ready(self, company_id: uuid.UUID) -> None:
        from src.common.database import engine as control_engine

        schema = schema_name_for(company_id)
        # CREATE SCHEMA on a plain connection; create tables through the
        # translate map so the symbolic "tenant" schema resolves to t_<hex>.
        async with control_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        async with control_engine.begin() as conn:
            tconn = await conn.execution_options(schema_translate_map={"tenant": schema})
            await self._create_tables(tconn)
        await self._seed_if_empty(company_id)

    @asynccontextmanager
    async def _schema_session(self, company_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
        from src.common.database import engine as control_engine

        schema = schema_name_for(company_id)
        # schema_translate_map qualifies "tenant.<table>" → "t_<hex>.<table>"
        # per session — leak-free (no connection-level SET search_path).
        engine = control_engine.execution_options(schema_translate_map={"tenant": schema})
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session

    # ------------------------------------------------------------------
    # container backend (prod — dedicated hb-tenant-db per tenant)
    # ------------------------------------------------------------------

    async def _ensure_container_ready(self, company_id: uuid.UUID) -> None:
        engine = await self._container_engine(company_id)
        # Dedicated DB: the symbolic "tenant" schema maps to the default public.
        async with engine.begin() as conn:
            tconn = await conn.execution_options(schema_translate_map={"tenant": None})
            await self._create_tables(tconn)
        await self._seed_if_empty(company_id)

    @asynccontextmanager
    async def _container_session(self, company_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
        base = await self._container_engine(company_id)
        engine = base.execution_options(schema_translate_map={"tenant": None})
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

    async def _seed_if_empty(self, company_id: uuid.UUID) -> None:
        from src.ai.tenant_schema.bootstrap import seed_hbs_spine

        async with (
            self._container_session(company_id)
            if self._backend == "container"
            else self._schema_session(company_id)
        ) as session:
            await seed_hbs_spine(session, company_id)
            await session.commit()


# Module singleton — reuse across the app.
tenant_data_plane = TenantDataPlane()


@asynccontextmanager
async def get_tenant_session(company_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Convenience wrapper over the module-singleton data plane."""
    async with tenant_data_plane.session(company_id) as session:
        yield session
