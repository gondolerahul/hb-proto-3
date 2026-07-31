"""trust/router.py — ``GET /ai/consent``, the registry read (D8 E1).

The tables (``consent_records``, ``dnc_entries``, ``unsubscribe_log``), the
registry that enforces them and migration ``trust001`` have all shipped
since Increment 2; nothing exposed them, so the Bridges board's gate panel
and the Undercroft's consent bay both rendered fixtures. This is the door.

Read-only on purpose. Writing consent is an act with a counterparty on the
other end of it — ``set_consent`` / ``add_dnc`` / ``record_unsubscribe``
are called by the flows that have the counterparty's word for it (an
unsubscribe click, a tenant's own posture change through the certified
``consent@1`` act), never by a panel that merely lists them.

Company-scoped from the session, never from a parameter (D5 §2.2, the
VG-05 lesson applied before the fact): there is no company selector to get
wrong here, and a cross-tenant read is not expressible on this surface.
"""
from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.trust.consent_read import MAX_ENTRIES, consent_view
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/consent", tags=["Consent"])


@router.get("")
async def get_consent(
    limit: int = Query(200, ge=1, le=MAX_ENTRIES),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """This company's consent posture and the rows behind it.

    ``channels`` is what a gate panel needs (posture, the registry's own
    reason, and the counts); ``entries`` is what the consent bay lists.
    """
    return await consent_view(
        db, cast(uuid.UUID, current_user.company_id), limit=limit)
