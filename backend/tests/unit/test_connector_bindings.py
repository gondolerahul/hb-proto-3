"""Inc 4 / CONN T2 (unit) — credential round-trip + the resolver contract.

The DB CRUD + rehydrate live in the integration test; here we prove the two
pieces that need no database: credentials encrypt/decrypt losslessly, and the
default resolver honours the own-adapter ``build`` contract while refusing an
un-wired MCP server transport (the §9 live-binding boundary).
"""
from __future__ import annotations

import pytest

from src.ai.connectors.catalog import AuthKind, ConnectorBackend, ConnectorDef
from src.ai.connectors.credentials import load_secret, store_secret
from src.ai.connectors.models import ConnectorBinding
from src.ai.connectors.resolver import (
    AdapterContractError,
    ConnectorTransportUnavailable,
    DefaultClientResolver,
)
from src.ai.tools.mcp.client import MCPCallResult, MCPToolDescriptor


def test_credentials_round_trip() -> None:
    creds = {"access_token": "tok-123", "refresh_token": "rt-456", "org_id": "9"}
    blob = store_secret(creds)
    assert "tok-123" not in blob  # encrypted, not plaintext
    assert load_secret(blob) == creds


def test_credentials_reject_non_object_blob() -> None:
    from src.common.security import encrypt_api_key

    with pytest.raises(ValueError):
        load_secret(encrypt_api_key('"just a string"'))


class _FakeClient:
    """Satisfies the MCPClient protocol structurally."""

    def __init__(self, credentials: dict[str, object]) -> None:
        self.credentials = credentials

    async def list_tools(self) -> list[MCPToolDescriptor]:
        return [MCPToolDescriptor(name="get_invoice", annotations={"readOnlyHint": True})]

    async def call_tool(self, name: str, arguments: dict[str, object]) -> MCPCallResult:
        return MCPCallResult(text="{}")


class _GoodAdapter:
    @classmethod
    def build(cls, credentials: dict[str, object], config: object) -> _FakeClient:
        return _FakeClient(credentials)


class _NoBuildAdapter:
    pass


def _binding(connector_id: str) -> ConnectorBinding:
    return ConnectorBinding(connector_id=connector_id, transport_config=None,
                            tool_allow=[], write_allow=[])


def _own_adapter_def() -> ConnectorDef:
    return ConnectorDef("fake_own", "finance", "Fake Own", ConnectorBackend.OWN_ADAPTER,
                        adapter="pkg.mod.Adapter", auth=AuthKind.OAUTH2, cost_sku="x")


def _mcp_server_def() -> ConnectorDef:
    return ConnectorDef("fake_srv", "finance", "Fake Srv", ConnectorBackend.MCP_SERVER,
                        server_ref="srv", cost_sku="x")


@pytest.mark.asyncio
async def test_resolver_builds_own_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.ai.connectors.resolver._import_attr", lambda _p: _GoodAdapter)
    resolver = DefaultClientResolver()
    client = await resolver.resolve(_own_adapter_def(), _binding("fake_own"), {"k": "v"})
    tools = await client.list_tools()
    assert tools[0].name == "get_invoice"


@pytest.mark.asyncio
async def test_resolver_rejects_adapter_without_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.ai.connectors.resolver._import_attr", lambda _p: _NoBuildAdapter)
    with pytest.raises(AdapterContractError):
        await DefaultClientResolver().resolve(_own_adapter_def(), _binding("fake_own"), {})


@pytest.mark.asyncio
async def test_resolver_refuses_unwired_mcp_server() -> None:
    with pytest.raises(ConnectorTransportUnavailable):
        await DefaultClientResolver().resolve(_mcp_server_def(), _binding("fake_srv"), {})
