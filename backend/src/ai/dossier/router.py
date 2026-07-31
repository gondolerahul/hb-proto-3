"""dossier/router.py — ``GET /ai/entities/{entity_id}/dossier`` (D8 E3).

The Dossier surface had no endpoint at all; it rendered a fixture. This is the
door. It sits under ``/ai/entities`` rather than in the legacy ``/ai`` router
because the read is a composed projection with its own honest-absence contract,
and it belongs beside ``GET /ai/entities/{entity_id}`` where the frontend
already looks for a colleague.

Read-only. Changing a charter is a governed act with a version ledger behind it
(``entity_versions``), not a PUT on a dossier.

Company-scoped from the session, never from a parameter (D5 §2.2, the VG-05
rule). A 404 answers unknown and cross-tenant alike, so a probe cannot learn
that an id exists in someone else's tenant.
"""
from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.dossier.read import dossier_view
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/entities", tags=["Dossier"])


@router.get("/{entity_id}/dossier")
async def get_dossier(
    entity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One colleague's terms of engagement.

    ``absent`` travels with the payload: it names, per field, what the platform
    cannot answer and why, so the surface renders a deliberate absence instead
    of finding an empty field and filling it in.
    """
    dossier = await dossier_view(
        db, cast(uuid.UUID, current_user.company_id), entity_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="Colleague not found")
    return dossier
