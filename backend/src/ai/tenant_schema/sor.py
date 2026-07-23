"""tenant_schema/sor.py — the system-of-record write-back seam (§21).

An externally-mastered object (``TenantEntityDef.sor.master == "external"``)
writes back **through its connector first**; the local mirror updates only on
confirmation (§21.2). The record service must reach a connector to do that, but
``tenant_schema`` must not import ``ai.connectors`` (a cycle). So the connector
side is a **pluggable provider** installed at boot — the same seam pattern KAR's
consent check uses (``solo_pack.consent.set_consent_checker``).

Until a provider is installed, an externally-mastered write **fails safe**: the
record service returns ``writeback_failed`` rather than writing a local mirror
the external master never saw.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import UUID

__all__ = [
    "SorDecl",
    "sor_of",
    "WriteBackResult",
    "WriteBackProvider",
    "set_writeback_provider",
    "get_writeback_provider",
]


@dataclass(frozen=True)
class SorDecl:
    """A def's parsed SoR declaration (§21.1)."""

    master: str                    # "hirebuddha" | "external"
    connector_id: Optional[str] = None
    write_back: bool = True

    @property
    def external(self) -> bool:
        return self.master == "external"


def sor_of(raw: Any) -> SorDecl:
    """Parse a def's ``sor`` JSON into a SorDecl; default HireBuddha-mastered.

    The standalone case is the norm (§21.3): an unset/malformed ``sor`` means
    HireBuddha masters the object, so a record write stays fully local.
    """
    if not isinstance(raw, dict):
        return SorDecl("hirebuddha")
    master = raw.get("master")
    if master != "external":
        return SorDecl("hirebuddha")
    return SorDecl(
        "external",
        connector_id=raw.get("connector_id"),
        write_back=bool(raw.get("write_back", True)),
    )


@dataclass(frozen=True)
class WriteBackResult:
    """What the connector reported for a write-back attempt."""

    ok: bool
    external_id: Optional[str] = None
    etag: Optional[str] = None
    # master-wins (§21.2): the external object changed under us; the local write
    # loses and a sync.conflict is raised rather than overwriting the mirror.
    conflict: bool = False
    error: Optional[str] = None


@runtime_checkable
class WriteBackProvider(Protocol):
    """The connector side of a write-back, installed at boot by ai.connectors."""

    async def write_back(
        self,
        *,
        company_id: UUID,
        connector_id: Optional[str],
        op: str,                       # "create" | "update" | "delete"
        object_name: str,              # the canonical HBS object (e.g. "Invoice")
        record_id: Optional[UUID],
        data: dict[str, Any],
        external_ref: Optional[dict[str, Any]],
    ) -> WriteBackResult:
        ...


_provider: Optional[WriteBackProvider] = None


def set_writeback_provider(provider: Optional[WriteBackProvider]) -> None:
    """Install (or clear) the connector-backed write-back provider."""
    global _provider
    _provider = provider


def get_writeback_provider() -> Optional[WriteBackProvider]:
    return _provider
