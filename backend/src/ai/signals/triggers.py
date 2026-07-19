"""signals/triggers.py — trigger-registry resolution (§18.3).

Exactly one owning Process per signal, made mechanical: among all enabled
registrations whose pattern matches the signal type, the winner is the
highest ``priority``; ties break deterministically on ``process_entity_id``.
Exact-vs-glob specificity is expressed through priority, not special-cased.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.signals.models import TriggerRegistration

__all__ = ["pattern_matches", "select_owner", "resolve_owner"]


def pattern_matches(pattern: str, signal_type: str) -> bool:
    """True when a registry pattern covers a signal type.

    ``"lead.inbound"`` — exact match only.
    ``"lead.*"``      — any type under the ``lead.`` prefix.
    ``"*"``           — everything.
    """
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return signal_type.startswith(pattern[:-1])
    return signal_type == pattern


def select_owner(
    registrations: list[TriggerRegistration], signal_type: str,
) -> TriggerRegistration | None:
    """Pure selection: best match by priority DESC, then entity id ASC."""
    matches = [r for r in registrations if r.enabled and pattern_matches(r.type_pattern, signal_type)]
    if not matches:
        return None
    matches.sort(key=lambda r: (-r.priority, str(r.process_entity_id), str(r.id)))
    return matches[0]


async def resolve_owner(
    db: AsyncSession, company_id: uuid.UUID, signal_type: str,
) -> TriggerRegistration | None:
    """Fetch the company's enabled registrations and pick the single owner."""
    rows = (await db.execute(
        select(TriggerRegistration).where(
            TriggerRegistration.company_id == company_id,
            TriggerRegistration.enabled.is_(True),
        )
    )).scalars().all()
    return select_owner(list(rows), signal_type)
