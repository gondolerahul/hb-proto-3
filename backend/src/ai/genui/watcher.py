"""genui/watcher.py — the approval watcher (STEWARD S1, 12_steward.md §4).

The production caller of ``channel.deliver_tray``. SEAM built the single
delivery door and shipped with the honest limit "nothing calls this in
production"; this module is the producer: a pending approval becomes a
delivered tray within one sweep interval, wherever the owner is.

Where it runs is forced, not chosen: the socket hub is in-memory in the API
process, so an arq cron cannot reach it — the watcher is an **asyncio task
started at app startup** (and the arq worker is a known single point of
failure that should not also be able to silence approvals).

A **sweep, not a creation hook** (the LEARN outcome-runner precedent): a
hook inside the gate would couple gate code to a UI concern and would miss
any approval created by a path that forgot the hook. The sweep selects
``PENDING`` approvals through the company join — the VG-05 shape — and
consults the delivery ledger.

The recipient set per approval: every user with an **open socket** in the
company's hub sessions ∪ every user with an **active push subscription**.
The ledger's (approval, user) grain does the rest — reached once, never
twice; appearing later, still told (see ``models.TrayDelivery``).

The loop must never die quietly — the repo's "nothing happened" rule says
that is exactly where this codebase hides its bugs — so one bad approval
logs and skips, one failed sweep logs and the loop survives, and a test
injects a raising sweep to prove it.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.genui.channel import deliver_tray, hub
from src.ai.genui.models import PushSubscription, TrayDelivery, TrayRecommendation
from src.ai.genui.trays import tray_detail
from src.ai.orm.execution import ExecutionRun, HumanApproval

logger = logging.getLogger(__name__)


@dataclass
class RecommendationDraft:
    """What the writer hands back. Spend is deliberately absent — the usage
    ledger (the TRAY_RECOMMENDATION attribution) is the one authority on
    cost, and a copy here would drift from it."""

    sentence: str
    model_used: str | None = None


#: (db, company_id, tray) -> a draft, or None. Installed by S2's
#: recommendation writer at boot; absent, trays deliver without one.
RecommendFn = Callable[
    [AsyncSession, uuid.UUID, dict[str, Any]],
    Awaitable["RecommendationDraft | None"]]

_recommender: RecommendFn | None = None


def install_recommender(fn: RecommendFn | None) -> None:
    global _recommender
    _recommender = fn


async def _pending_approvals(
    db: AsyncSession,
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """(approval_id, company_id) for every PENDING approval, oldest first."""
    rows = (
        await db.execute(
            select(HumanApproval.id, ExecutionRun.company_id)
            .join(ExecutionRun, HumanApproval.run_id == ExecutionRun.id)
            .where(HumanApproval.status == "PENDING")
            .order_by(HumanApproval.requested_at)
        )
    ).all()
    return [(approval_id, company_id) for approval_id, company_id in rows]


async def _delivered_pairs(
    db: AsyncSession, approval_ids: list[uuid.UUID],
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    if not approval_ids:
        return set()
    rows = (
        await db.execute(
            select(TrayDelivery.approval_id, TrayDelivery.user_id)
            .where(TrayDelivery.approval_id.in_(approval_ids))
        )
    ).all()
    return {(approval_id, user_id) for approval_id, user_id in rows}


async def _push_users(
    db: AsyncSession, company_id: uuid.UUID,
) -> set[uuid.UUID]:
    rows = (
        await db.execute(
            select(PushSubscription.user_id)
            .where(
                PushSubscription.company_id == company_id,
                PushSubscription.revoked_at.is_(None),
            )
            .distinct()
        )
    ).scalars().all()
    return set(rows)


async def _recommendation_for(
    db: AsyncSession,
    company_id: uuid.UUID,
    approval_id: uuid.UUID,
    tray: dict[str, Any],
    *,
    first_delivery: bool,
) -> str | None:
    """The stored sentence if one exists; else — only before anyone has been
    reached — ask the installed writer once and store what it says. Once a
    tray has gone out without a recommendation it stays without one (§5:
    advice appearing under a card the owner already read reads as the
    platform changing its mind after the fact). Failure → None, loudly
    logged, and the tray delivers anyway — advice lost, never work."""
    existing = await db.get(TrayRecommendation, approval_id)
    if existing is not None:
        return existing.sentence
    if not first_delivery or _recommender is None:
        return None
    try:
        draft = await _recommender(db, company_id, tray)
    except Exception:  # noqa: BLE001 — a broken writer must not block a tray
        logger.warning(
            "tray recommendation failed for approval %s", approval_id,
            exc_info=True)
        return None
    if draft is None:
        return None
    db.add(TrayRecommendation(
        approval_id=approval_id, company_id=company_id,
        sentence=draft.sentence, model_used=draft.model_used))
    return draft.sentence


async def sweep_once(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    push_transport: Any = None,
) -> list[TrayDelivery]:
    """One pass: every PENDING approval, every reachable not-yet-reached
    user. Returns the ledger rows written (committed before returning).

    The hub is deliberately the module global (via ``hub()``) rather than a
    parameter — ``deliver_tray`` reads the same global, and letting a caller
    pass a *different* hub here would make "who is listening" and "who gets
    the socket" silently disagree. Tests patch ``channel._hub``."""
    channel_hub = hub()
    now = now or datetime.utcnow()

    pending = await _pending_approvals(db)
    if not pending:
        return []
    delivered = await _delivered_pairs(db, [a for a, _ in pending])

    push_users_by_company: dict[uuid.UUID, set[uuid.UUID]] = {}
    written: list[TrayDelivery] = []

    for approval_id, company_id in pending:
        try:
            if company_id not in push_users_by_company:
                push_users_by_company[company_id] = await _push_users(
                    db, company_id)
            reachable = (
                channel_hub.users_with_open_sockets(company_id)
                | push_users_by_company[company_id]
            )
            targets = {
                user_id for user_id in reachable
                if (approval_id, user_id) not in delivered
            }
            if not targets:
                continue

            tray = await tray_detail(db, company_id, approval_id, now=now)
            if tray is None:
                continue
            first_delivery = not any(
                a == approval_id for a, _ in delivered)
            tray["recommendation"] = await _recommendation_for(
                db, company_id, approval_id, tray,
                first_delivery=first_delivery)

            for user_id in targets:
                via = await deliver_tray(
                    db, company_id, user_id, tray,
                    push_transport=push_transport)
                if via in ("socket", "push"):
                    row = TrayDelivery(
                        approval_id=approval_id, company_id=company_id,
                        user_id=user_id, via=via, delivered_at=now)
                    db.add(row)
                    written.append(row)
                    delivered.add((approval_id, user_id))
        except Exception:  # noqa: BLE001 — one bad approval must not stop the rest
            logger.warning(
                "tray delivery sweep failed for approval %s", approval_id,
                exc_info=True)

    await db.commit()
    return written


async def watcher_loop(
    *,
    interval: float,
    stop: asyncio.Event,
    sweep: Callable[[], Awaitable[object]] | None = None,
) -> None:
    """The lifespan task. A failed sweep logs and the loop survives — a
    silent dead watcher is the failure mode the tripwire test exists for."""
    while not stop.is_set():
        try:
            if sweep is not None:
                await sweep()
            else:
                from src.common.database import AsyncSessionLocal

                async with AsyncSessionLocal() as db:
                    await sweep_once(db)
        except Exception:  # noqa: BLE001 — the loop must outlive any one sweep
            logger.exception("tray watcher sweep failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


_task: asyncio.Task[None] | None = None
_stop = asyncio.Event()


def start_tray_watcher(interval: float) -> None:
    """Called from the API app's startup hook — and only from there, because
    only that process holds the socket hub."""
    global _task
    if _task is not None and not _task.done():
        return
    _stop.clear()
    _task = asyncio.get_event_loop().create_task(
        watcher_loop(interval=interval, stop=_stop))


async def stop_tray_watcher() -> None:
    global _task
    _stop.set()
    if _task is not None:
        try:
            await asyncio.wait_for(_task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _task.cancel()
    _task = None
