"""connectors/models.py — persisted per-company connector bindings (CONN T2).

The shipped ``MCPServerBinding`` (``ai.tools.mcp.adapter``) is an in-memory
dataclass: a bound server evaporates on restart. This table makes a binding
durable so it can be rehydrated into that live seam (the ``register_solo_pack_tools``
entry-point pattern), and holds the per-company credential.

**Credential storage is inline** (``encrypted_secret``), matching the shipped
``config.IntegrationRegistry.encrypted_api_key`` pattern rather than a second
table — a binding is 1:1 with its credential (per company, per connector), so a
join buys nothing. The secret is an AES-256-GCM blob of a JSON credential set
(``common.security.encrypt_api_key``), so an OAuth token set stores the same way
as a bare API key.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

# FK target must be registered with the metadata before mapper configuration
# (same rule as signals/models.py + ai/orm/__init__.py).
from src.auth.models import Company  # noqa: F401

__all__ = ["ConnectorBinding", "BindingStatus"]


class BindingStatus:
    ACTIVE = "active"    # rehydrated into the live seam; tools bindable
    PAUSED = "paused"    # persisted but not bound (tenant or dunning paused it)
    ERROR = "error"      # last (re)bind failed; see last_error, emits incident.platform


class ConnectorBinding(Base):
    """One company's binding of one catalog connector (§6.6)."""

    __tablename__ = "connector_bindings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    # The catalog connector_id (catalog.CONNECTOR_CATALOG). Not an FK — the
    # catalog is code-resident data, validated by the service on write.
    connector_id: Mapped[str] = mapped_column(String(48), nullable=False)

    # Transport for an MCP_SERVER backend (stdio cmd / HTTP or SSE URL); None
    # for an OWN_ADAPTER (the adapter class is named in the catalog).
    transport_config: Mapped[Any] = mapped_column(JSON, nullable=True)
    # Per-company tool policy (§ MCPServerBinding). Empty allow = all listed.
    tool_allow: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    write_allow: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)

    # AES-256-GCM(JSON creds) — the API key or OAuth token set. Never logged.
    encrypted_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_sku: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(String(12), nullable=False, default=BindingStatus.ACTIVE)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LIB T8 (Inc 6, VG-16). `status` records that a binding *has* broken;
    # nothing recorded that one is *about to*. An OAuth token expiring at 3am
    # on a Sunday becomes a silent, total outage of that connector until
    # somebody notices the work stopped. NULL means "no expiry known" — which
    # is honest for an API key that genuinely has none, and is why the sweep
    # skips NULLs rather than treating them as expired.
    credentials_expire_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "connector_id", name="uq_connector_bindings_company_connector"),
    )
