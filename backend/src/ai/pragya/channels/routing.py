"""pragya/channels/routing.py — which face answers the phone (Inc-4 T5).

Decision 5: **the number is the routing discriminator.** An inbound call
resolves by *destination*, and that single fact keeps the two voice faces from
ever being confused at the entry point:

* → **Pragya's number** — the inward face. ASR-LLM-TTS, caller identified by
  a verified ``channel_bindings`` row, T1 ceiling, voice can never self-elevate.
* → **the tenant's business number** — KAR-01. Realtime speech-to-speech,
  counterparty trust, the collapsed-loop profile.

Deciding by destination rather than by caller matters because the caller is
the untrusted half. A discriminator that depended on *who called* would be a
discriminator an attacker chooses; the number they dialled is not.

A number is Pragya's when it is assigned to the tenant's Pragya entity. That
reuses the shipped ``phone_numbers`` lifecycle (``available → claimed →
assigned``) rather than adding a parallel flag that could disagree with it.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional, cast

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.orm.entity import HierarchicalEntity
from src.ai.pragya.children import PRAGYA_ENTITY_NAMES
from src.voice.phone_pool_models import PhoneNumber

logger = logging.getLogger(__name__)

__all__ = ["VoiceFace", "NumberRoute", "number_candidates", "route_for_number",
           "pragya_entity_for", "assign_pragya_number"]


class VoiceFace(str, Enum):
    """Which pipeline answers."""

    PRAGYA = "pragya"      # inward: the owner calling their account manager
    GATEWAY = "gateway"    # outward: a customer calling the business
    UNKNOWN = "unknown"    # the number is not assigned to anyone


@dataclass(frozen=True)
class NumberRoute:
    face: VoiceFace
    company_id: uuid.UUID | None = None
    entity_id: uuid.UUID | None = None
    reason: str = ""


def number_candidates(phone_number: str) -> list[str]:
    """Formats a carrier might send the same number in.

    Twilio sends ``+918065251146`` and Tata may send ``918065251146``; the DB
    holds one of them. Matching a set is what stops a routing miss looking
    like an unassigned number.
    """
    if not phone_number:
        return []
    clean = phone_number.replace(" ", "").replace("-", "").strip()
    candidates = [clean]
    if clean.startswith("+"):
        candidates.append(clean[1:])
    else:
        candidates.append(f"+{clean}")
    return candidates


async def pragya_entity_for(
    db: AsyncSession, company_id: uuid.UUID,
) -> HierarchicalEntity | None:
    """The tenant's Pragya entity, if one is seeded."""
    return (await db.execute(
        select(HierarchicalEntity).where(
            HierarchicalEntity.company_id == company_id,
            or_(*[HierarchicalEntity.name.ilike(f"%{n}%")
                  for n in PRAGYA_ENTITY_NAMES]),
        ).limit(1)
    )).scalars().first()


async def route_for_number(
    db: AsyncSession, dialled_number: str,
) -> NumberRoute:
    """Decide which face answers a call to ``dialled_number``.

    Fails to ``UNKNOWN`` rather than guessing a face. An unassigned number
    reaching the inward pipeline would offer an account-manager conversation
    on a line nobody owns.
    """
    candidates = number_candidates(dialled_number)
    if not candidates:
        return NumberRoute(VoiceFace.UNKNOWN, reason="no number supplied")

    assigned = (await db.execute(
        select(PhoneNumber).where(
            or_(*[PhoneNumber.phone_number == c for c in candidates]),
            PhoneNumber.status == "assigned",
            PhoneNumber.is_active.is_(True),
        ).limit(1)
    )).scalars().first()

    if assigned is None:
        return NumberRoute(
            VoiceFace.UNKNOWN,
            reason=f"{dialled_number} is not assigned to anyone")

    company_id = cast(Optional[uuid.UUID], assigned.company_id)
    entity_id = cast(Optional[uuid.UUID], assigned.agent_id)

    if company_id is None:
        return NumberRoute(
            VoiceFace.UNKNOWN, reason="assigned number has no company")

    pragya = await pragya_entity_for(db, company_id)
    if pragya is not None and entity_id is not None and entity_id == pragya.id:
        return NumberRoute(
            VoiceFace.PRAGYA, company_id=company_id, entity_id=entity_id,
            reason="assigned to the tenant's account manager")

    return NumberRoute(
        VoiceFace.GATEWAY, company_id=company_id, entity_id=entity_id,
        reason="assigned to a business-facing agent")


async def assign_pragya_number(
    db: AsyncSession, *, company_id: uuid.UUID, phone_number: str,
) -> PhoneNumber:
    """Point a claimed number at the tenant's Pragya entity.

    Refuses rather than improvising when there is no Pragya entity: a number
    routed to the inward face with nothing behind it answers and then cannot
    hold a conversation.
    """
    pragya = await pragya_entity_for(db, company_id)
    if pragya is None:
        raise ValueError(
            "no Pragya entity is seeded for this company — assign the number "
            "after she exists, or the inward face has nothing behind it")

    candidates = number_candidates(phone_number)
    row = (await db.execute(
        select(PhoneNumber).where(
            or_(*[PhoneNumber.phone_number == c for c in candidates]),
        ).limit(1)
    )).scalars().first()
    if row is None:
        raise ValueError(f"{phone_number} is not in the phone pool")

    # PhoneNumber is a legacy Column-style model with no static attribute
    # types, so writes go through setattr rather than fighting the stubs.
    setattr(row, "company_id", company_id)
    setattr(row, "agent_id", pragya.id)
    setattr(row, "status", "assigned")
    setattr(row, "is_active", True)
    setattr(row, "label", "Pragya (account manager)")
    await db.flush()
    logger.info("assigned %s to Pragya for company %s", phone_number, company_id)
    return row
