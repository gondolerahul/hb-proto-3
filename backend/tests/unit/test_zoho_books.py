"""Inc 4 / CONN T6 (unit) — the Zoho Books adapter against a fake transport.

Proves the adapter's two contracts over a faked HTTP surface (no live call — the
§9 boundary): write-back maps canonical→Zoho and parses the id/etag back, a 409
is a master-wins conflict, a 4xx is a failure; fetch_changes turns Zoho invoices
into SyncEvents; and the MCPClient tool surface lists + dispatches.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

from src.ai.connectors.zoho_books.client import ZohoBooksClient


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Optional[dict[str, Any]], Optional[dict[str, Any]]]] = []
        self.responses: list[tuple[int, dict[str, Any]]] = []

    def enqueue(self, status: int, body: dict[str, Any]) -> None:
        self.responses.append((status, body))

    async def __call__(
        self, method: str, path: str,
        json_body: Optional[dict[str, Any]], params: Optional[dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        self.calls.append((method, path, json_body, params))
        return self.responses.pop(0) if self.responses else (200, {})


def _client(t: _FakeTransport) -> ZohoBooksClient:
    return ZohoBooksClient(access_token="tok", org_id="ORG1", transport=t)


@pytest.mark.asyncio
async def test_writeback_create_maps_and_parses() -> None:
    t = _FakeTransport()
    t.enqueue(200, {"invoice": {"invoice_id": "Z1", "last_modified_time": "T1"}})
    res = await _client(t).write_back(
        op="create", object_name="Invoice",
        data={"invoice_number": "INV-1", "total": 100, "account": "ignored-ref"},
        external_ref=None)
    assert res.ok and res.external_id == "Z1" and res.etag == "T1"
    method, path, body, params = t.calls[0]
    assert method == "POST" and path == "/invoices"
    assert body == {"invoice_number": "INV-1", "total": 100}   # ref not pushed
    assert params["organization_id"] == "ORG1"


@pytest.mark.asyncio
async def test_writeback_update_targets_external_id() -> None:
    t = _FakeTransport()
    t.enqueue(200, {"invoice": {"invoice_id": "Z1", "last_modified_time": "T2"}})
    res = await _client(t).write_back(
        op="update", object_name="Invoice", data={"status": "paid"},
        external_ref={"external_id": "Z1", "etag": "T1"})
    assert res.ok and res.etag == "T2"
    assert t.calls[0][0] == "PUT" and t.calls[0][1] == "/invoices/Z1"


@pytest.mark.asyncio
async def test_writeback_409_is_master_wins_conflict() -> None:
    t = _FakeTransport()
    t.enqueue(409, {})
    res = await _client(t).write_back(
        op="update", object_name="Invoice", data={"status": "paid"},
        external_ref={"external_id": "Z1"})
    assert res.ok is False and res.conflict is True


@pytest.mark.asyncio
async def test_writeback_4xx_is_failure() -> None:
    t = _FakeTransport()
    t.enqueue(400, {"message": "invalid"})
    res = await _client(t).write_back(
        op="create", object_name="Invoice", data={"invoice_number": "X"}, external_ref=None)
    assert res.ok is False and res.conflict is False and "invalid" in (res.error or "")


@pytest.mark.asyncio
async def test_writeback_rejects_unmastered_object() -> None:
    res = await _client(_FakeTransport()).write_back(
        op="create", object_name="Vendor", data={}, external_ref=None)
    assert res.ok is False and "Vendor" in (res.error or "")


@pytest.mark.asyncio
async def test_fetch_changes_maps_to_sync_events() -> None:
    t = _FakeTransport()
    t.enqueue(200, {"invoices": [
        {"invoice_id": "Z1", "last_modified_time": "T1", "invoice_number": "INV-1", "status": "sent"},
    ]})
    events = await _client(t).fetch_changes("Invoice", since="T0")
    assert len(events) == 1
    ev = events[0]
    assert ev.object_name == "Invoice" and ev.external_id == "Z1" and ev.etag == "T1"
    assert ev.data == {"invoice_number": "INV-1", "status": "sent"}
    assert ev.event_id == "zoho:Z1:T1"
    assert t.calls[0][3]["last_modified_time"] == "T0"


@pytest.mark.asyncio
async def test_tool_surface() -> None:
    tools = {d.name: d for d in await _client(_FakeTransport()).list_tools()}
    assert set(tools) == {"get_invoice", "list_invoices", "create_invoice", "update_invoice"}
    assert tools["get_invoice"].read_only is True
    assert tools["create_invoice"].read_only is False   # a write → needs write_allow


@pytest.mark.asyncio
async def test_call_tool_dispatches_read() -> None:
    t = _FakeTransport()
    t.enqueue(200, {"invoice": {"invoice_id": "Z1"}})
    res = await _client(t).call_tool("get_invoice", {"invoice_id": "Z1"})
    assert res.is_error is False and "Z1" in res.text
    assert t.calls[0][0] == "GET" and t.calls[0][1] == "/invoices/Z1"


def test_build_from_credentials() -> None:
    c = ZohoBooksClient.build({"access_token": "tok", "org_id": "ORG9"}, None)
    assert isinstance(c, ZohoBooksClient)
