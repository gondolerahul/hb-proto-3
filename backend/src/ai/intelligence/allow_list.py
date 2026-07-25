"""intelligence/allow_list.py — the D5 effective allow-list (FLEET).

    effective_allow(company) = { providers default-allowed } ∪ { providers opted into }

The default-allowed set is a *catalog* fact (`model_registry.data_flow.default_allowed`)
— the providers already in production use. Everything else (GLM/Qwen/Kimi, all
China-hosted) is registered but off until the tenant opts in against the current
data-flow disclosure version.

The router calls ``effective_allow`` to build ``signals.allow_list``, and
``RegistryService.eligible`` / ``IntelligenceRouter._candidates`` filter on it
**before scoring** — so a disallowed provider is never a candidate, not merely a
low-scoring one. The read is live: a revoke bites on the very next call.

Design: docs/product-road-map/increment-5/03_fleet_expansion.md §3.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.intelligence.models import CompanyProviderOptin, ModelRegistry

__all__ = [
    "CURRENT_DISCLOSURE_VERSION", "DisclosureError",
    "default_allowed_providers", "opted_in_providers", "effective_allow",
    "opt_in", "revoke",
]

# Bump when increment-5/03a_data_flow_disclosure.md changes materially. An
# opt-in recorded against an older version no longer counts as informed consent.
#: Bumped 2026-07-25 for the Increment-6 LEARN section (§6 — what the platform
#: learns across tenants). Existing opt-in rows keep working: the version is
#: checked when an opt-in is *recorded*, not on every routing call, so a bump
#: means the next person to opt in must have read the current text rather than
#: that anyone loses access.
CURRENT_DISCLOSURE_VERSION = "2026-07-25"


class DisclosureError(Exception):
    """An opt-in was attempted without acknowledging the current disclosure."""


async def default_allowed_providers(db: AsyncSession) -> set[str]:
    """Providers the catalog marks default-allowed (the conservative set)."""
    rows = (await db.execute(select(ModelRegistry))).scalars().all()
    out: set[str] = set()
    for r in rows:
        flow: dict[str, Any] = r.data_flow or {}
        if flow.get("default_allowed") is True:
            out.add(r.provider)
    return out


async def opted_in_providers(db: AsyncSession, company_id: uuid.UUID) -> set[str]:
    """Providers this company has a live (un-revoked) opt-in for."""
    rows = (await db.execute(
        select(CompanyProviderOptin).where(
            CompanyProviderOptin.company_id == company_id,
            CompanyProviderOptin.revoked_at.is_(None),
        )
    )).scalars().all()
    return {r.provider for r in rows}


async def effective_allow(db: AsyncSession, company_id: uuid.UUID) -> set[str]:
    """The providers this company's router may consider at all (D5)."""
    return (await default_allowed_providers(db)) | (await opted_in_providers(db, company_id))


async def opt_in(
    db: AsyncSession, company_id: uuid.UUID, provider: str, *,
    disclosure_version: str, user_id: uuid.UUID | None = None,
) -> CompanyProviderOptin:
    """Record a tenant's informed opt-in. Refuses a stale/absent disclosure
    version — you cannot accept terms you have not seen."""
    if disclosure_version != CURRENT_DISCLOSURE_VERSION:
        raise DisclosureError(
            f"disclosure version '{disclosure_version}' is not the current "
            f"'{CURRENT_DISCLOSURE_VERSION}' — re-read the data-flow disclosure before opting in")

    row = (await db.execute(
        select(CompanyProviderOptin).where(
            CompanyProviderOptin.company_id == company_id,
            CompanyProviderOptin.provider == provider,
        )
    )).scalar_one_or_none()

    if row is None:
        row = CompanyProviderOptin(
            company_id=company_id, provider=provider,
            disclosure_version=disclosure_version, opted_in_by=user_id,
            opted_in_at=datetime.utcnow(), revoked_at=None)
        db.add(row)
    else:  # re-opt-in: clear the revoke, restamp the acknowledgement
        row.disclosure_version = disclosure_version
        row.opted_in_by = user_id
        row.opted_in_at = datetime.utcnow()
        row.revoked_at = None
    await db.commit()
    return row


async def revoke(db: AsyncSession, company_id: uuid.UUID, provider: str) -> bool:
    """Withdraw an opt-in. Takes effect on the next routing call (live read)."""
    row = (await db.execute(
        select(CompanyProviderOptin).where(
            CompanyProviderOptin.company_id == company_id,
            CompanyProviderOptin.provider == provider,
            CompanyProviderOptin.revoked_at.is_(None),
        )
    )).scalar_one_or_none()
    if row is None:
        return False
    row.revoked_at = datetime.utcnow()
    await db.commit()
    return True
