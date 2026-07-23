"""Inc 4 / CONN T1 — the §6.6 connector catalog is valid + well-formed.

The catalog is code-resident data (like ``solo_pack.bundles``), so CI proves it
is internally consistent: unique ids, a backend that resolves to a reachable
implementation, and ``masters`` that name real objects. Binding is not exercised
here — that is T2.
"""
from __future__ import annotations

from src.ai.connectors.catalog import (
    CONNECTOR_CATALOG,
    AuthKind,
    ConnectorBackend,
    connector_by_id,
    connectors_for_domain,
    connectors_mastering,
)

# The 27-object HBS spine (tenant_schema/hbs_seed). masters must draw from it.
HBS_OBJECTS = {
    "Account", "Asset/Inventory Item", "Bill", "Budget", "Campaign", "Candidate",
    "Contact", "Contract", "Deliverable", "Employee", "Evidence", "Incident",
    "Invoice", "Lead", "Ledger Entry", "Opportunity", "Order", "Payment",
    "Policy/Obligation", "Product/SKU", "Project/Engagement", "Purchase Order",
    "Quote", "Risk", "Signal", "Ticket", "Vendor",
}


def test_catalog_is_non_empty() -> None:
    assert len(CONNECTOR_CATALOG) >= 15


def test_connector_ids_are_unique() -> None:
    ids = [c.connector_id for c in CONNECTOR_CATALOG]
    assert len(ids) == len(set(ids))


def test_every_entry_is_described() -> None:
    for c in CONNECTOR_CATALOG:
        assert c.connector_id and c.domain and c.display_name


def test_masters_are_real_hbs_objects() -> None:
    for c in CONNECTOR_CATALOG:
        for obj in c.masters:
            assert obj in HBS_OBJECTS, f"{c.connector_id} masters unknown object {obj!r}"


def test_backend_resolves_to_an_implementation() -> None:
    """MCP servers name a server_ref; own-adapters name an adapter path."""
    for c in CONNECTOR_CATALOG:
        if c.backend is ConnectorBackend.MCP_SERVER:
            assert c.server_ref, f"{c.connector_id} MCP_SERVER without a server_ref"
        elif c.backend is ConnectorBackend.OWN_ADAPTER:
            assert c.adapter, f"{c.connector_id} OWN_ADAPTER without an adapter path"


def test_platform_internal_is_not_bindable() -> None:
    for c in CONNECTOR_CATALOG:
        if c.backend is ConnectorBackend.PLATFORM_INTERNAL:
            assert not c.bindable
            assert c.auth is AuthKind.INTERNAL
        else:
            assert c.bindable


def test_bindable_connectors_carry_a_cost_sku() -> None:
    """Every externally-bound connector meters against an `mcp` SKU."""
    for c in CONNECTOR_CATALOG:
        if c.bindable:
            assert c.cost_sku, f"{c.connector_id} is bindable but has no cost_sku"


def test_zoho_books_is_the_accounting_flagship() -> None:
    zoho = connector_by_id("zoho_books")
    assert zoho is not None
    assert zoho.backend is ConnectorBackend.OWN_ADAPTER
    assert zoho.auth is AuthKind.OAUTH2
    assert "Invoice" in zoho.masters
    assert zoho.adapter == "src.ai.connectors.zoho_books.client.ZohoBooksClient"
    # write-back tools are curated (read-only-first): destructive create/update
    # are opted in by default for the flagship.
    assert "update_invoice" in zoho.default_write_allow


def test_lookup_helpers() -> None:
    assert connector_by_id("does_not_exist") is None
    finance = connectors_for_domain("finance")
    assert {c.connector_id for c in finance} >= {"zoho_books", "plaid_bank_feed"}
    invoice_masters = {c.connector_id for c in connectors_mastering("Invoice")}
    assert "zoho_books" in invoice_masters
