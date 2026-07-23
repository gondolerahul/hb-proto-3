"""connectors/resolver.py — construct a live MCPClient for a binding.

This is the seam where the **live-binding boundary** (02_conn_sor.md §9) lives.
A persisted :class:`~src.ai.connectors.models.ConnectorBinding` names *what* to
bind; a resolver turns it into a live :class:`~src.ai.tools.mcp.client.MCPClient`.

Two backends:

* ``OWN_ADAPTER`` — import the catalog's adapter class and build it from the
  decrypted credentials. Own-adapters implement ``MCPClient`` **and** expose a
  ``build(credentials, config) -> MCPClient`` classmethod (the adapter contract).
* ``MCP_SERVER`` — construct the official-SDK transport (stdio/HTTP/SSE) from
  ``transport_config``. That wire-level work is deliberately deferred until a
  deployment has a reachable server + credentials (§9); the default resolver
  raises :class:`ConnectorTransportUnavailable` for it. Tests inject a fake
  resolver, so the rest of the machine is provable without a live transport.
"""
from __future__ import annotations

import importlib
from typing import Any, Protocol, cast, runtime_checkable

from src.ai.connectors.catalog import ConnectorBackend, ConnectorDef
from src.ai.connectors.models import ConnectorBinding
from src.ai.tools.mcp.client import MCPClient

__all__ = [
    "ClientResolver",
    "DefaultClientResolver",
    "ConnectorTransportUnavailable",
    "AdapterContractError",
]


class ConnectorTransportUnavailable(RuntimeError):
    """An MCP_SERVER transport is not wired for this deployment (the §9 boundary)."""


class AdapterContractError(RuntimeError):
    """An OWN_ADAPTER class does not satisfy the ``build(...)`` contract."""


@runtime_checkable
class ClientResolver(Protocol):
    """Turns a persisted binding into a live MCPClient."""

    async def resolve(
        self, connector: ConnectorDef, binding: ConnectorBinding, credentials: dict[str, Any],
    ) -> MCPClient:
        ...


def _import_attr(dotted: str) -> Any:
    """Import ``pkg.mod.Attr`` and return the attribute."""
    module_path, _, attr = dotted.rpartition(".")
    if not module_path:
        raise AdapterContractError(f"adapter path is not fully qualified: {dotted!r}")
    module = importlib.import_module(module_path)
    return getattr(module, attr)


class DefaultClientResolver:
    """The production resolver — own-adapters build now; servers await transport."""

    async def resolve(
        self, connector: ConnectorDef, binding: ConnectorBinding, credentials: dict[str, Any],
    ) -> MCPClient:
        if connector.backend is ConnectorBackend.OWN_ADAPTER:
            if not connector.adapter:
                raise AdapterContractError(f"{connector.connector_id} declares no adapter path")
            adapter_cls = _import_attr(connector.adapter)
            build = getattr(adapter_cls, "build", None)
            if build is None:
                raise AdapterContractError(
                    f"{connector.adapter} must expose a build(credentials, config) classmethod")
            client = build(credentials, binding.transport_config)
            return cast(MCPClient, client)
        if connector.backend is ConnectorBackend.MCP_SERVER:
            raise ConnectorTransportUnavailable(
                f"{connector.connector_id}: MCP server transport not wired "
                "(live-binding boundary — 02_conn_sor.md §9)")
        raise ConnectorTransportUnavailable(
            f"{connector.connector_id} is platform-internal and not bindable")
