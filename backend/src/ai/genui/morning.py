"""genui/morning.py — the Morning Story, composed (LINE L1, VG-20).

The story is the Standup told in the pocket: one card per colleague, the
one who needs the owner first, quiet days last. VG-20 sketched "a daily
narrative generation job"; the assessment found the narrative already
existed — DRIVER's Standup composes it client-side from three shipped
reads — so this module **ports that composition server-side** (the audio
job needs it there) and keeps it a projection over the estate's truth.
The sentences here and in ``StandupSurface.tsx`` must tell the same story;
if the two ever drift, the phone and the desk disagree about yesterday,
and the fix is here.

The read path (``morning_story``): a stored row for today — written by
L2's job, its audio aligned to its cards — is served as-is, because the
story is *the morning's telling*, not a live view (the Standup is the
live view). No row → compose fresh, text-only, with the absence named
(``degraded_reason: "not_generated"``) rather than silent.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.genui.estate import estate_view
from src.ai.genui.trays import _pending_with_entities
from src.ai.orm.execution import ExecutionRun

__all__ = ["compose_morning_story", "morning_story"]


def compose_morning_story(
    estate: dict[str, Any],
    runs: Iterable[tuple[str, str]],
    waiting_entity_ids: set[str],
    now: datetime,
) -> list[dict[str, Any]]:
    """One card per colleague. Pure — the Standup's composition, ported.

    ``runs`` are ``(entity_id, status)`` pairs already bounded to the last
    day; the counting lives here so the job and the endpoint cannot count
    differently.
    """
    completed: dict[str, int] = {}
    failed: dict[str, int] = {}
    running: dict[str, int] = {}
    for entity_id, status in runs:
        if status == "COMPLETED":
            completed[entity_id] = completed.get(entity_id, 0) + 1
        elif status == "FAILED":
            failed[entity_id] = failed.get(entity_id, 0) + 1
        elif status == "RUNNING":
            running[entity_id] = running.get(entity_id, 0) + 1

    cards: list[dict[str, Any]] = []
    for district in estate.get("districts", []):
        for colleague in district.get("colleagues", []):
            entity_id = str(colleague.get("entity_id"))
            sentences: list[str] = []
            done = completed.get(entity_id, 0)
            if done == 1:
                sentences.append("Finished one piece of work since yesterday.")
            elif done > 1:
                sentences.append(
                    f"Finished {done} pieces of work since yesterday.")
            wrong = failed.get(entity_id, 0)
            if wrong == 1:
                sentences.append("One thing went wrong — it is in the trace.")
            elif wrong > 1:
                sentences.append(
                    f"{wrong} things went wrong — they are in the traces.")
            if running.get(entity_id, 0) > 0:
                sentences.append("Is working on something right now.")
            waiting = entity_id in waiting_entity_ids
            if waiting:
                sentences.append("Is waiting on you.")
            if not sentences:
                sentences.append("A quiet day — nothing to report.")
            cards.append({
                "entity_id": entity_id,
                "name": colleague.get("name"),
                "district": district.get("process_code"),
                "sentences": sentences,
                "waiting": waiting,
                # The job fills this; a fresh composition honestly has none.
                "audio": None,
            })
    # Whoever needs the owner comes first; quiet days come last.
    cards.sort(key=lambda card: (not card["waiting"]))
    return cards


async def _runs_since_yesterday(
    db: AsyncSession, company_id: uuid.UUID, now: datetime,
) -> list[tuple[str, str]]:
    rows = (
        await db.execute(
            select(ExecutionRun.entity_id, ExecutionRun.status)
            .where(
                ExecutionRun.company_id == company_id,
                ExecutionRun.created_at >= now - timedelta(days=1),
            ))
    ).all()
    return [(str(entity_id), str(status)) for entity_id, status in rows]


async def compose_for_company(
    db: AsyncSession, company_id: uuid.UUID, *, now: datetime,
) -> list[dict[str, Any]]:
    """The three shipped reads, then the pure composition — shared by the
    endpoint's fresh path and L2's job so they cannot drift."""
    estate = await estate_view(db, company_id, now=now)
    runs = await _runs_since_yesterday(db, company_id, now)
    waiting = {
        str(entity_id)
        for _approval, entity_id, _name in await _pending_with_entities(
            db, company_id)
    }
    return compose_morning_story(estate, runs, waiting, now)


async def morning_story(
    db: AsyncSession, company_id: uuid.UUID, *, now: datetime | None = None,
) -> dict[str, Any]:
    """Today's story for the Line."""
    now = now or datetime.utcnow()
    story_date: date = now.date()

    from src.ai.genui.models import MorningStory

    row = await db.get(MorningStory, (company_id, story_date))
    if row is not None:
        return {
            "story_date": story_date.isoformat(),
            "cards": row.cards,
            "generated_at": row.generated_at.isoformat(),
            "degraded_reason": row.degraded_reason,
        }
    cards = await compose_for_company(db, company_id, now=now)
    return {
        "story_date": story_date.isoformat(),
        "cards": cards,
        "generated_at": None,
        "degraded_reason": "not_generated",
    }
