"""twin/replay.py — real history, real code path, isolated writes (TWIN T5).

Selects the signals that actually happened in a tenant's window and re-runs
them against the twin plane at a chosen entity version.

**What replay is not.** ``POST /ai/signals/{id}/replay`` already exists in
`signals/api.py` and replays a signal into the **live** plane. That is an
operational retry — useful, and nothing to do with this. A future reader will
find it and think the replay engine was already built; the difference is
isolation, and it is the whole difference.

**Replay is not determinism.** The same signal re-run through the same agent
with the same model does not produce the same tokens. What the `replay` grade
promises is narrower and true: *the inputs were real events that actually
happened, the code path was the real one, and the writes went nowhere.* See
`twin.grading` — the claim is stated in three places because a surface will
otherwise claim more than the engine can support.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.twin.materialise import Scope

logger = logging.getLogger(__name__)

__all__ = ["ReplaySelection", "select_signals", "replay"]


@dataclass
class ReplaySelection:
    """The real events a scenario will re-run."""

    signal_ids: tuple[uuid.UUID, ...] = ()
    types: dict[str, int] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.signal_ids)


async def select_signals(
    db: AsyncSession, company_id: uuid.UUID, scope: Scope, *,
    types: Optional[Sequence[str]] = None, limit: int = 500,
) -> ReplaySelection:
    """The signals inside the scenario's window, newest first.

    Bounded by ``limit`` as well as by the window. The window cap is a refusal
    (§6.1) because a silently shortened *window* makes two runs incomparable;
    a signal-count bound is different in kind — it is a cost ceiling on a busy
    tenant's week, and it is reported on the result rather than hidden.
    """
    from src.ai.signals.models import Signal

    since = datetime.utcnow() - timedelta(days=scope.window_days)
    query = (
        select(Signal)
        .where(Signal.company_id == company_id, Signal.created_at >= since)
        .order_by(Signal.created_at.desc())
        .limit(limit)
    )
    if types:
        query = query.where(Signal.type.in_(list(types)))

    rows = (await db.execute(query)).scalars().all()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.type] = counts.get(row.type, 0) + 1
    return ReplaySelection(tuple(r.id for r in rows), counts)


@dataclass
class ReplayResult:
    signals_replayed: int
    simulated_calls: int
    external_effects: int
    by_category: dict[str, int]
    truncated: bool


async def replay(
    db: AsyncSession, company_id: uuid.UUID, scope: Scope, *,
    handler: Any, types: Optional[Sequence[str]] = None, limit: int = 500,
) -> ReplayResult:
    """Re-run the window's real signals through ``handler``.

    ``handler`` is injected rather than reached for. It is what makes this
    testable without standing up the whole agent loop, and — more importantly —
    it is what keeps this module from being the second place that knows how to
    dispatch a signal. The dispatcher is shipped; TWIN selects and counts.

    The handler is expected to have been built over
    :func:`twin.substitution.substituted_registry`, which is what makes the
    writes go nowhere. That coupling is asserted by the T6 mutation test rather
    than by a check here — a check would be one more thing to forget, and the
    substituted registry is a different object, not a flag.
    """
    from src.ai.twin.substitution import CallRecorder

    selection = await select_signals(db, company_id, scope, types=types, limit=limit)
    recorder: CallRecorder = getattr(handler, "recorder", None) or CallRecorder()

    replayed = 0
    for signal_id in selection.signal_ids:
        try:
            await handler(signal_id)
            replayed += 1
        except Exception as exc:  # noqa: BLE001
            # One signal failing is a data point about the change, not a
            # reason to abandon the rehearsal. A scenario that dies on the
            # first awkward event tells the tenant nothing.
            logger.debug("[twin] replay of signal %s failed: %s", signal_id, exc)

    return ReplayResult(
        signals_replayed=replayed,
        simulated_calls=len(recorder.calls),
        external_effects=recorder.external_effects,
        by_category=recorder.by_category(),
        truncated=len(selection) >= limit,
    )
