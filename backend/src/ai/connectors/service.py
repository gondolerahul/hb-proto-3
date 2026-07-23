"""connectors/service.py — activate / pause / rehydrate a company's bindings.

The service is the write side of CONN: it validates a connector against the
catalog, stores the credential encrypted, and persists the binding — then
rehydrates ACTIVE bindings into the shipped live seam (``bind_mcp_server``),
which registers each connector tool as an EXPERIMENTAL tenant tool under the
normal cost/attribution wrappers.

Rehydration is **lazy, per company** (not a global boot sweep): the platform
hibernates idle tenants, and the §18 dispatcher parks — never drops — a signal
for a waking tenant, so binding on first connector activity fits the lifecycle.
The live transport itself is resolved by an injected :class:`ClientResolver`, so
the persistence + rehydrate logic is provable against a fake client without any
external server (the §9 live-binding boundary).
"""
from __future__ import annotations

import logging
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.connectors.catalog import connector_by_id
from src.ai.connectors.credentials import store_secret
from src.ai.connectors.models import BindingStatus, ConnectorBinding
from src.ai.connectors.resolver import ClientResolver, DefaultClientResolver
from src.ai.tools.mcp.adapter import MCPServerBinding, MCPToolAdapter, bind_mcp_server

logger = logging.getLogger(__name__)

__all__ = ["ConnectorService", "UnknownConnector", "ConnectorNotBindable"]


class UnknownConnector(ValueError):
    """No catalog entry for the given connector_id."""


class ConnectorNotBindable(ValueError):
    """The connector is platform-internal — it has no external binding."""


class ConnectorService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_binding(self, company_id: UUID, connector_id: str) -> ConnectorBinding | None:
        result = await self.db.execute(
            select(ConnectorBinding).where(
                ConnectorBinding.company_id == company_id,
                ConnectorBinding.connector_id == connector_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_bindings(
        self, company_id: UUID, *, status: str | None = None,
    ) -> list[ConnectorBinding]:
        stmt = select(ConnectorBinding).where(ConnectorBinding.company_id == company_id)
        if status is not None:
            stmt = stmt.where(ConnectorBinding.status == status)
        result = await self.db.execute(stmt)
        rows: Sequence[ConnectorBinding] = result.scalars().all()
        return list(rows)

    async def activate(
        self,
        company_id: UUID,
        connector_id: str,
        *,
        credentials: dict[str, Any] | None = None,
        transport_config: dict[str, Any] | None = None,
        tool_allow: Sequence[str] | None = None,
        write_allow: Sequence[str] | None = None,
    ) -> ConnectorBinding:
        """Create or update an ACTIVE binding for ``connector_id``.

        ``write_allow`` defaults to the catalog's ``default_write_allow`` (the
        read-only-first posture: destructive tools are opted in, not on by
        default). ``credentials`` are encrypted before they touch the row.
        """
        connector = connector_by_id(connector_id)
        if connector is None:
            raise UnknownConnector(connector_id)
        if not connector.bindable:
            raise ConnectorNotBindable(connector_id)

        secret = store_secret(credentials) if credentials else None
        allow_writes = (
            list(write_allow) if write_allow is not None
            else list(connector.default_write_allow)
        )
        allow_tools = list(tool_allow) if tool_allow is not None else []

        binding = await self.get_binding(company_id, connector_id)
        if binding is None:
            binding = ConnectorBinding(
                company_id=company_id,
                connector_id=connector_id,
                transport_config=transport_config,
                tool_allow=allow_tools,
                write_allow=allow_writes,
                encrypted_secret=secret,
                cost_sku=connector.cost_sku,
                status=BindingStatus.ACTIVE,
            )
            self.db.add(binding)
        else:
            binding.transport_config = transport_config
            binding.tool_allow = allow_tools
            binding.write_allow = allow_writes
            if secret is not None:
                binding.encrypted_secret = secret
            binding.cost_sku = connector.cost_sku
            binding.status = BindingStatus.ACTIVE
            binding.last_error = None
        await self.db.commit()
        await self.db.refresh(binding)
        return binding

    async def pause(self, company_id: UUID, connector_id: str) -> ConnectorBinding | None:
        binding = await self.get_binding(company_id, connector_id)
        if binding is None:
            return None
        binding.status = BindingStatus.PAUSED
        await self.db.commit()
        await self.db.refresh(binding)
        return binding

    async def to_live_binding(
        self, binding: ConnectorBinding, resolver: ClientResolver,
    ) -> MCPServerBinding:
        """Assemble the in-memory ``MCPServerBinding`` seam object for a row."""
        from src.ai.connectors.credentials import load_secret

        connector = connector_by_id(binding.connector_id)
        if connector is None:
            raise UnknownConnector(binding.connector_id)
        creds = load_secret(binding.encrypted_secret) if binding.encrypted_secret else {}
        client = await resolver.resolve(connector, binding, creds)
        return MCPServerBinding(
            server_name=binding.connector_id,
            client=client,
            tool_allow=list(binding.tool_allow or []),
            write_allow=list(binding.write_allow or []),
        )

    async def rehydrate(
        self,
        company_id: UUID,
        *,
        resolver: ClientResolver | None = None,
        register: bool = True,
    ) -> list[MCPToolAdapter]:
        """Bind every ACTIVE binding for ``company_id`` into the live tool seam.

        A binding whose transport cannot be resolved is marked ERROR (with the
        reason on ``last_error``) and skipped — one bad connector never fails
        the others, and never crashes boot.
        """
        resolver = resolver or DefaultClientResolver()
        adapters: list[MCPToolAdapter] = []
        for binding in await self.list_bindings(company_id, status=BindingStatus.ACTIVE):
            try:
                live = await self.to_live_binding(binding, resolver)
                bound = await bind_mcp_server(company_id, live, register=register)
                adapters.extend(bound)
            except Exception as exc:  # noqa: BLE001 — one connector must not sink the rest
                logger.warning("connector rehydrate failed: %s/%s: %s",
                               company_id, binding.connector_id, exc)
                binding.status = BindingStatus.ERROR
                binding.last_error = f"{type(exc).__name__}: {exc}"
                await self.db.commit()
        return adapters
