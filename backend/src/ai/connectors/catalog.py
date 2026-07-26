"""connectors.catalog — the §6.6 connector manifest (Increment 4 / CONN T1).

One :class:`ConnectorDef` per functional-doc §6.6 row, hand-authored like the
Solo Pack's ``bundles.py`` — code-resident data, not a table. Registering a row
here is data; *binding* it for a company (T2) is the live, credentialed step.

Three backends (decision 3, 2026-07-23):

* ``MCP_SERVER``  — a real external MCP server over the official SDK transport.
  Preferred where a credible server exists.
* ``OWN_ADAPTER`` — an :class:`~src.ai.tools.mcp.client.MCPClient`-conforming
  class we write, wrapping a vendor REST API (Zoho Books) or a shipped
  in-repo tool (social). Same read-only-first posture, same seam.
* ``PLATFORM_INTERNAL`` — a §6.6 row already backed by a shipped platform
  primitive (Chronos, Tenant Data Query, OCR, ...). Cataloged for completeness
  (decision 1 — the *full* §6.6 catalog); it needs no external credential and
  is not bindable as an external connector.

``masters`` names the canonical HBS objects (from the 27-object spine) a
connector *can* master under SOR (§21). It is capability, not assignment: the
tenant declares one master per object via ``TenantEntityDef.sor`` — several
connectors may list the same object, and the tenant picks one.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "ConnectorBackend",
    "AuthKind",
    "ConnectorDef",
    "CONNECTOR_CATALOG",
    "connector_by_id",
    "connectors_for_domain",
    "connectors_mastering",
]


class ConnectorBackend(str, Enum):
    """How a connector's tools are reached (decision 3)."""

    MCP_SERVER = "mcp_server"
    OWN_ADAPTER = "own_adapter"
    PLATFORM_INTERNAL = "platform_internal"


class AuthKind(str, Enum):
    """How a binding authenticates to the external system."""

    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    GATEWAY = "gateway"    # on-prem/desktop bridge (e.g. a Tally local gateway)
    INTERNAL = "internal"  # shipped platform primitive; no external credential


@dataclass(frozen=True)
class ConnectorDef:
    """One §6.6 connector — a catalog entry, bindable per company."""

    connector_id: str
    domain: str
    display_name: str
    backend: ConnectorBackend
    # Canonical HBS objects this connector can master under SOR (§21). Empty =
    # a pure read/feed/annotate service that masters no object.
    masters: tuple[str, ...] = ()
    # MCP_SERVER: the published server package / URL hint. OWN_ADAPTER: the
    # dotted path to the MCPClient impl. PLATFORM_INTERNAL / TBD: None.
    server_ref: str | None = None
    adapter: str | None = None
    # Destructive tool names permitted by default (usually empty — write-back
    # tools are opted into per binding via write_allow; read-only-first).
    default_write_allow: tuple[str, ...] = ()
    auth: AuthKind = AuthKind.API_KEY
    cost_sku: str | None = None  # IntegrationRegistry SKU for `mcp` metering

    @property
    def bindable(self) -> bool:
        """True when this is an external connector a company can bind."""
        return self.backend is not ConnectorBackend.PLATFORM_INTERNAL


# --------------------------------------------------------------------------- #
# The catalog — every §6.6 row (functional doc §6.6). Accounting is Zoho Books
# (decision 2), the reference OWN_ADAPTER. External servers are MCP_SERVER;
# shipped primitives are PLATFORM_INTERNAL.
# --------------------------------------------------------------------------- #
CONNECTOR_CATALOG: tuple[ConnectorDef, ...] = (
    # --- Finance & Accounting -------------------------------------------- #
    ConnectorDef(
        "zoho_books", "finance", "Zoho Books (Accounting)",
        ConnectorBackend.OWN_ADAPTER,
        masters=("Invoice", "Bill", "Payment", "Contact"),
        adapter="src.ai.connectors.zoho_books.client.ZohoBooksClient",
        default_write_allow=("create_invoice", "update_invoice"),
        auth=AuthKind.OAUTH2, cost_sku="mcp-zoho-books",
    ),
    ConnectorDef(
        "plaid_bank_feed", "finance", "Bank Feed Synchronizer",
        ConnectorBackend.MCP_SERVER, server_ref="plaid",
        auth=AuthKind.OAUTH2, cost_sku="mcp-plaid",
    ),
    ConnectorDef(
        "stripe_payouts", "finance", "Global Payout Rails",
        ConnectorBackend.MCP_SERVER, masters=("Payment",), server_ref="stripe",
        auth=AuthKind.API_KEY, cost_sku="mcp-stripe-payouts",
    ),
    ConnectorDef(
        "avalara_tax", "finance", "Automated Tax Matrix",
        ConnectorBackend.MCP_SERVER, server_ref="avalara",
        auth=AuthKind.API_KEY, cost_sku="mcp-avalara",
    ),
    # --- Legal & Compliance ---------------------------------------------- #
    ConnectorDef(
        "docusign_esign", "legal", "Cryptographic E-Signature Handler",
        ConnectorBackend.MCP_SERVER, masters=("Contract",), server_ref="docusign",
        auth=AuthKind.OAUTH2, cost_sku="mcp-docusign",
    ),
    ConnectorDef(
        "middesk_kyb", "legal", "Entity Identity Verification Gateway",
        ConnectorBackend.MCP_SERVER, server_ref="middesk",
        auth=AuthKind.API_KEY, cost_sku="mcp-middesk",
    ),
    # --- Human Orchestration --------------------------------------------- #
    ConnectorDef(
        "slack_comms", "human_orchestration", "Rich Communication Broker",
        ConnectorBackend.MCP_SERVER, server_ref="slack",
        auth=AuthKind.OAUTH2, cost_sku="mcp-slack",
    ),
    ConnectorDef(
        "jira_helpdesk", "human_orchestration", "Internal Helpdesk Route-and-Lock",
        ConnectorBackend.MCP_SERVER, masters=("Ticket",), server_ref="jira",
        auth=AuthKind.OAUTH2, cost_sku="mcp-jira",
    ),
    # --- Sales & Marketing ----------------------------------------------- #
    ConnectorDef(
        "apollo_enrichment", "sales", "Enrichment & Signal Harvester",
        ConnectorBackend.MCP_SERVER, server_ref="apollo",
        auth=AuthKind.API_KEY, cost_sku="mcp-apollo",
    ),
    ConnectorDef(
        "google_calendar", "sales", "Calendar Matrix Orchestrator",
        ConnectorBackend.MCP_SERVER, server_ref="google-calendar",
        auth=AuthKind.OAUTH2, cost_sku="mcp-gcal",
    ),
    ConnectorDef(
        "social_publishing", "sales", "Social Publishing & Listening",
        ConnectorBackend.OWN_ADAPTER,
        adapter="src.ai.social_connection_service",
        auth=AuthKind.OAUTH2, cost_sku="mcp-social",
    ),
    # --- Operations & HR / Supply Chain ---------------------------------- #
    ConnectorDef(
        "gusto_hris", "operations", "HRIS Core Accessor",
        ConnectorBackend.MCP_SERVER, masters=("Employee",), server_ref="gusto",
        auth=AuthKind.OAUTH2, cost_sku="mcp-gusto",
    ),
    ConnectorDef(
        "shipstation_inventory", "operations", "Warehousing & Inventory Oracle",
        ConnectorBackend.MCP_SERVER,
        masters=("Asset/Inventory Item", "Order"), server_ref="shipstation",
        auth=AuthKind.API_KEY, cost_sku="mcp-shipstation",
    ),
    # --- Knowledge & Onboarding ------------------------------------------ #
    ConnectorDef(
        "notion_knowledge", "knowledge", "Knowledge Source Connectors",
        ConnectorBackend.MCP_SERVER, server_ref="notion",
        auth=AuthKind.OAUTH2, cost_sku="mcp-notion",
    ),
    # LIB T7 (Inc 6) — connected drives, VG-14. Both declare **no masters**:
    # a drive masters no HBS object. It is a source of documents, not of
    # records, so the Inc-4 mastering machinery deliberately does not engage
    # and `connectors/document_sync.py` handles it instead of `sync.py`.
    ConnectorDef(
        "sharepoint_drive", "knowledge", "Knowledge Source Connectors",
        ConnectorBackend.MCP_SERVER, server_ref="sharepoint",
        auth=AuthKind.OAUTH2, cost_sku="mcp-sharepoint",
    ),
    ConnectorDef(
        "google_drive", "knowledge", "Knowledge Source Connectors",
        ConnectorBackend.MCP_SERVER, server_ref="gdrive",
        auth=AuthKind.OAUTH2, cost_sku="mcp-gdrive",
    ),
    # --- Business Systems (generic enterprise SoR bridges) --------------- #
    ConnectorDef(
        "crm_generic", "business_systems", "Enterprise CRM Connector",
        ConnectorBackend.MCP_SERVER,
        masters=("Account", "Contact", "Lead", "Opportunity"),
        server_ref="crm", auth=AuthKind.OAUTH2, cost_sku="mcp-crm",
    ),
    ConnectorDef(
        "erp_generic", "business_systems", "Enterprise ERP Connector",
        ConnectorBackend.MCP_SERVER,
        masters=("Product/SKU", "Purchase Order", "Order"),
        server_ref="erp", auth=AuthKind.OAUTH2, cost_sku="mcp-erp",
    ),
    # --- Platform Primitives (shipped; cataloged for completeness) ------- #
    ConnectorDef(
        "chronos_daemon", "platform", "Chronos Daemon (delayed callbacks)",
        ConnectorBackend.PLATFORM_INTERNAL, auth=AuthKind.INTERNAL,
    ),
    ConnectorDef(
        "tenant_data_query", "platform", "Tenant Data Query (read-only SQL)",
        ConnectorBackend.PLATFORM_INTERNAL, auth=AuthKind.INTERNAL,
    ),
    ConnectorDef(
        "document_ocr", "platform", "Document Extraction & OCR",
        ConnectorBackend.PLATFORM_INTERNAL, auth=AuthKind.INTERNAL,
    ),
    ConnectorDef(
        "translation", "platform", "Translation & Localization",
        ConnectorBackend.PLATFORM_INTERNAL, auth=AuthKind.INTERNAL,
    ),
    ConnectorDef(
        "evidence_store", "platform", "Evidence Store",
        ConnectorBackend.PLATFORM_INTERNAL,
        masters=("Evidence",), auth=AuthKind.INTERNAL,
    ),
    ConnectorDef(
        "alerting", "platform", "Alerting & Notification",
        ConnectorBackend.PLATFORM_INTERNAL, auth=AuthKind.INTERNAL,
    ),
)


# Fail fast on a duplicate id — the manifest is the source of truth.
_seen: set[str] = set()
for _c in CONNECTOR_CATALOG:
    if _c.connector_id in _seen:
        raise ValueError(f"duplicate connector_id in catalog: {_c.connector_id}")
    _seen.add(_c.connector_id)
del _seen, _c


def connector_by_id(connector_id: str) -> ConnectorDef | None:
    """Return the catalog entry with ``connector_id``, or None."""
    for connector in CONNECTOR_CATALOG:
        if connector.connector_id == connector_id:
            return connector
    return None


def connectors_for_domain(domain: str) -> tuple[ConnectorDef, ...]:
    """All catalog entries in ``domain`` (e.g. ``"finance"``)."""
    return tuple(c for c in CONNECTOR_CATALOG if c.domain == domain)


def connectors_mastering(object_name: str) -> tuple[ConnectorDef, ...]:
    """All catalog entries that can master the canonical ``object_name``."""
    return tuple(c for c in CONNECTOR_CATALOG if object_name in c.masters)
