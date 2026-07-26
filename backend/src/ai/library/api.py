"""library/api.py — the Library read surface (LIB T6, with T3's influence read).

Two reads, both narrow:

* **`/ai/documents/{id}/passage`** — opens a citation *at the passage*. This is
  the endpoint that makes a citation followable rather than decorative.
* **`/ai/documents/{id}/influence`** — what a document has actually done,
  answered off the daily rollup rather than by scanning the raw log.

**Neither takes a company id from the caller.** Both derive it from the session
and scope the query by it. Increment 6 has now fixed two cross-tenant reads
that were shaped exactly like these — VG-05's approval IDOR and SEGA T0's tool
registry — and both had the same cause: an id from the request used without
the scope from the session.

Design: docs/product-road-map/increment-6/06_lib.md §5.3, §7.2.
"""
from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.library.citations import read_passage
from src.ai.library.influence import influence_for_document
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/documents", tags=["Library"])


@router.get("/{document_id}/passage")
async def get_passage(
    document_id: uuid.UUID,
    chunk: int = Query(0, ge=0, description="The cited chunk index"),
    context: int = Query(1, ge=0, le=5,
                         description="Neighbouring chunks either side"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The cited chunk plus its neighbours, with the document's provenance.

    404 on a cross-tenant miss, never 403: a probe must not learn that an id
    exists in another tenant (the VG-05 rule, stated in HANDOFF §5).
    """
    passage = await read_passage(
        db, cast(uuid.UUID, current_user.company_id), document_id,
        chunk_index=chunk, context=context)
    if passage is None:
        raise HTTPException(status_code=404, detail="Passage not found")
    return passage


@router.get("/{document_id}/influence")
async def get_influence(
    document_id: uuid.UUID,
    days: int = Query(30, ge=1, le=400),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """How much this document has shaped answers over a window.

    Reads `document_influence_daily`, so it is a small indexed aggregate rather
    than a scan of the raw usage log — which is also why it can only answer as
    far back as the rollup has run, and never further back than the log itself
    was started (LIB T2, 2026-07-25).
    """
    return await influence_for_document(
        db, cast(uuid.UUID, current_user.company_id), document_id, days=days)
