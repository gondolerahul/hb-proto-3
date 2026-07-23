"""connectors/writeback.py — the bridge from the SOR seam to a live connector.

``tenant_schema.sor`` defines the ``WriteBackProvider`` seam the record service
calls; this is the connector-backed implementation, installed at boot
(``install_connector_writeback`` — the ``install_consent_registry`` pattern). It
resolves the company's binding, gets the live client, and delegates to the
client's :class:`SorConnector` methods — so every vendor specific lives in the
adapter and this bridge stays connector-agnostic.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import UUID

from src.ai.connectors.catalog import connector_by_id
from src.ai.connectors.credentials import load_secret
from src.ai.connectors.models import BindingStatus
from src.ai.connectors.resolver import ClientResolver, DefaultClientResolver
from src.ai.connectors.service import ConnectorService
from src.ai.connectors.sync import SyncEvent
from src.ai.tenant_schema.sor import WriteBackResult, set_writeback_provider
from src.ai.tools.mcp.client import MCPClient

logger = logging.getLogger(__name__)

__all__ = ["SorConnector", "ConnectorWriteBackProvider", "install_connector_writeback"]


@runtime_checkable
class SorConnector(Protocol):
    """An own-adapter that can master objects: write-back + a change feed."""

    async def write_back(
        self, *, op: str, object_name: str, data: dict[str, Any],
        external_ref: Optional[dict[str, Any]],
    ) -> WriteBackResult:
        ...

    async def fetch_changes(self, object_name: str, since: Optional[str]) -> list[SyncEvent]:
        ...


class ConnectorWriteBackProvider:
    """Resolve the company's live connector and delegate the write-back to it.

    Satisfies ``tenant_schema.sor.WriteBackProvider``. Any resolution failure
    (no binding, not active, transport un-wired, not a SoR connector) returns a
    non-ok result rather than raising — the record service then reports
    ``writeback_failed`` and writes nothing locally (fail-safe, §21.2).
    """

    def __init__(self, resolver: Optional[ClientResolver] = None) -> None:
        self._resolver = resolver or DefaultClientResolver()

    async def write_back(
        self, *, company_id: UUID, connector_id: Optional[str], op: str,
        object_name: str, record_id: Optional[UUID], data: dict[str, Any],
        external_ref: Optional[dict[str, Any]],
    ) -> WriteBackResult:
        if not connector_id:
            return WriteBackResult(ok=False, error="externally-mastered object has no connector_id")
        client = await self._resolve_client(company_id, connector_id)
        if client is None:
            return WriteBackResult(ok=False, error=f"no active binding for {connector_id}")
        if not isinstance(client, SorConnector):
            return WriteBackResult(ok=False, error=f"{connector_id} is not a SoR connector")
        try:
            return await client.write_back(
                op=op, object_name=object_name, data=data, external_ref=external_ref)
        except Exception as exc:  # noqa: BLE001 — a connector fault is a failed write-back, not a crash
            logger.warning("write-back call failed (%s/%s): %s", connector_id, object_name, exc)
            return WriteBackResult(ok=False, error=f"{type(exc).__name__}: {exc}")

    async def _resolve_client(
        self, company_id: UUID, connector_id: str,
    ) -> Optional[MCPClient]:
        from src.common.database import AsyncSessionLocal

        connector = connector_by_id(connector_id)
        if connector is None:
            return None
        async with AsyncSessionLocal() as db:
            binding = await ConnectorService(db).get_binding(company_id, connector_id)
            if binding is None or binding.status != BindingStatus.ACTIVE:
                return None
            creds = load_secret(binding.encrypted_secret) if binding.encrypted_secret else {}
            try:
                return await self._resolver.resolve(connector, binding, creds)
            except Exception as exc:  # noqa: BLE001
                logger.warning("connector resolve failed (%s): %s", connector_id, exc)
                return None


def install_connector_writeback(resolver: Optional[ClientResolver] = None) -> None:
    """Install the connector-backed write-back provider into the SOR seam."""
    set_writeback_provider(ConnectorWriteBackProvider(resolver))
