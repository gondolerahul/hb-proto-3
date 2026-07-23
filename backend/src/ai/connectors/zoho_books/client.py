"""zoho_books/client.py — the Zoho Books adapter (MCPClient + SorConnector).

Speaks two contracts over one Zoho Books REST surface:

* **MCPClient** (``list_tools``/``call_tool``) — the agent tool path, so an
  agent can read/write Zoho through the normal governed tool wrappers.
* **SorConnector** (``write_back``/``fetch_changes``) — the mastering path the
  SOR write-back provider and the sweep delegate to.

HTTP is an injected ``Transport`` callable ``(method, path, json, params) ->
(status, body)``; the default is a thin httpx client, but tests inject a fake so
the adapter is provable without a live call (the §9 boundary).
"""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Optional

from src.ai.connectors.sync import SyncEvent
from src.ai.connectors.zoho_books.mapping import from_zoho_invoice, to_zoho_invoice
from src.ai.tenant_schema.sor import WriteBackResult
from src.ai.tools.mcp.client import MCPCallResult, MCPToolDescriptor

__all__ = ["ZohoBooksClient", "Transport"]

# (method, path, json_body, query_params) -> (status_code, response_body)
Transport = Callable[
    [str, str, Optional[dict[str, Any]], Optional[dict[str, Any]]],
    Awaitable[tuple[int, dict[str, Any]]],
]

_BASE_URL = "https://www.zohoapis.com/books/v3"

_TOOLS: list[MCPToolDescriptor] = [
    MCPToolDescriptor("get_invoice", "Fetch one invoice by id.",
                      {"type": "object", "properties": {"invoice_id": {"type": "string"}}},
                      {"readOnlyHint": True}),
    MCPToolDescriptor("list_invoices", "List invoices (optionally modified since).",
                      {"type": "object", "properties": {"last_modified_time": {"type": "string"}}},
                      {"readOnlyHint": True}),
    MCPToolDescriptor("create_invoice", "Create an invoice.",
                      {"type": "object"}, {}),
    MCPToolDescriptor("update_invoice", "Update an invoice by id.",
                      {"type": "object", "properties": {"invoice_id": {"type": "string"}}}, {}),
]


def _httpx_transport(access_token: str) -> Transport:
    """The live transport (the §9 boundary — untested here, needs a real token)."""
    async def _call(
        method: str, path: str,
        json_body: Optional[dict[str, Any]], params: Optional[dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        import httpx

        headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
        async with httpx.AsyncClient(base_url=_BASE_URL, headers=headers, timeout=30.0) as c:
            resp = await c.request(method, path, json=json_body, params=params)
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                body = {}
            return resp.status_code, body if isinstance(body, dict) else {"data": body}
    return _call


class ZohoBooksClient:
    """Adapts Zoho Books to the platform's connector contracts."""

    def __init__(
        self, *, access_token: str = "", org_id: str = "",
        transport: Optional[Transport] = None,
    ) -> None:
        self._org_id = org_id
        self._transport = transport or _httpx_transport(access_token)

    @classmethod
    def build(cls, credentials: dict[str, Any], config: Optional[dict[str, Any]]) -> "ZohoBooksClient":
        cfg = config or {}
        return cls(
            access_token=str(credentials.get("access_token", "")),
            org_id=str(cfg.get("org_id") or credentials.get("org_id", "")),
        )

    def _params(self, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        p: dict[str, Any] = {"organization_id": self._org_id}
        if extra:
            p.update({k: v for k, v in extra.items() if v is not None})
        return p

    # --- MCPClient (agent tool path) ----------------------------------- #

    async def list_tools(self) -> list[MCPToolDescriptor]:
        return _TOOLS

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        try:
            if name == "get_invoice":
                status, body = await self._transport(
                    "GET", f"/invoices/{arguments.get('invoice_id')}", None, self._params())
            elif name == "list_invoices":
                status, body = await self._transport(
                    "GET", "/invoices", None,
                    self._params({"last_modified_time": arguments.get("last_modified_time")}))
            elif name == "create_invoice":
                status, body = await self._transport(
                    "POST", "/invoices", to_zoho_invoice(arguments), self._params())
            elif name == "update_invoice":
                status, body = await self._transport(
                    "PUT", f"/invoices/{arguments.get('invoice_id')}",
                    to_zoho_invoice(arguments), self._params())
            else:
                return MCPCallResult(text=f"unknown tool {name}", is_error=True)
        except Exception as exc:  # noqa: BLE001
            return MCPCallResult(text=f"zoho call failed: {exc}", is_error=True)
        return MCPCallResult(text=json.dumps(body), is_error=status >= 400)

    # --- SorConnector (mastering path) --------------------------------- #

    async def write_back(
        self, *, op: str, object_name: str, data: dict[str, Any],
        external_ref: Optional[dict[str, Any]],
    ) -> WriteBackResult:
        if object_name != "Invoice":
            return WriteBackResult(ok=False, error=f"zoho_books does not master {object_name}")
        payload = to_zoho_invoice(data)
        if op == "create":
            status, body = await self._transport("POST", "/invoices", payload, self._params())
        else:
            ext_id = (external_ref or {}).get("external_id")
            status, body = await self._transport(
                "PUT", f"/invoices/{ext_id}", payload, self._params())
        # Zoho returns 409 when the record changed under an optimistic update.
        if status == 409:
            return WriteBackResult(ok=False, conflict=True)
        if status >= 400:
            return WriteBackResult(ok=False, error=f"zoho {status}: {body.get('message', '')}")
        inv = body.get("invoice", body)
        return WriteBackResult(
            ok=True, external_id=str(inv.get("invoice_id", "")),
            etag=str(inv.get("last_modified_time", "")),
        )

    async def fetch_changes(self, object_name: str, since: Optional[str]) -> list[SyncEvent]:
        if object_name != "Invoice":
            return []
        status, body = await self._transport(
            "GET", "/invoices", None, self._params({"last_modified_time": since}))
        if status >= 400:
            return []
        out: list[SyncEvent] = []
        for inv in body.get("invoices", []):
            iid, mtime = str(inv.get("invoice_id", "")), str(inv.get("last_modified_time", ""))
            out.append(SyncEvent(
                "Invoice", iid, from_zoho_invoice(inv), etag=mtime,
                event_id=f"zoho:{iid}:{mtime}",
            ))
        return out
