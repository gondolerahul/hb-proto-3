"""evolution/taint.py — a run's accumulated trust level, resolved at the gate (D3).

The ladder and the firewall are pure (``taint_firewall``); this is the part
that has to look at what a run has actually done.

**Resolved at the enforcement point, from the durable tool log.** The obvious
alternative is to thread a taint value down through the loop, the step executor
and the tool executor, updating it as results arrive. That plumbing crosses
three layers, and one of them — ``core/agent_loop.py`` — is pinned at its line
cap. Worse, an in-memory value does not survive a paused-and-resumed run, which
is exactly the shape a HITL-gated run has: the approval arrives hours later, in
a different process, and the context that made the act risky must still be
known.

``tool_interaction_logs`` already records every tool a run called. Reading it at
the gate costs one query *per categorised act* — and categorised acts are the
rare ones (payouts, contracts, outbound comms), not every step. A run that
never proposes an external effect never pays for this at all.

Design: docs/product-road-map/increment-6/02_sega.md §7.3.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.evolution.taint_firewall import descend, level_for_source, source_for_tool

logger = logging.getLogger(__name__)

__all__ = ["resolve_run_taint", "record_run_taint"]


async def resolve_run_taint(
    db: AsyncSession, run_id: Any, *, seed: str | None,
) -> str | None:
    """The run's current trust level: its seed, lowered by everything it read.

    ``seed`` is the triggering signal's trust (Increment 1's §18.6 field). From
    there the level only descends — there is no path back up, because the only
    honest way to raise trust is a human reading the content, and that is a
    HITL card rather than a state transition.

    Returns ``seed`` unchanged if anything goes wrong. Failing to the seed
    rather than to "untrusted" is deliberate: the taint lookup is a
    *refinement*, and a database hiccup must not start blocking payouts that
    the shipped rules allow — the gate above it already fails open for the same
    reason.
    """
    if run_id is None:
        return seed

    try:
        from src.ai.orm.execution import ToolInteractionLog

        tool_names = (await db.execute(
            select(ToolInteractionLog.tool_name).where(
                ToolInteractionLog.run_id == run_id)
        )).scalars().all()
    except Exception as exc:  # noqa: BLE001
        logger.debug("taint: could not read the tool log for %s: %s", run_id, exc)
        return seed

    level = seed
    for tool_name in tool_names:
        source = source_for_tool(tool_name)
        if source is None:
            continue                       # brings no external content in
        level = descend(level, level_for_source(source))
    return level


async def record_run_taint(
    db: AsyncSession, run_id: Any, level: str | None,
) -> None:
    """Stamp the resolved level onto the run, for the audit trail.

    A column rather than a ``context_state`` key because ``context_state`` is
    rewritten wholesale by the loop, and the question *"what did this run know
    when it asked?"* is one an incident review asks months later.

    Never raises: an audit stamp must not be able to fail an act that policy
    has already allowed.
    """
    if run_id is None or level is None:
        return
    try:
        from src.ai.orm.execution import ExecutionRun

        run = (await db.execute(
            select(ExecutionRun).where(ExecutionRun.id == run_id)
        )).scalar_one_or_none()
        if run is not None and run.taint_level != level:
            run.taint_level = level
    except Exception as exc:  # noqa: BLE001
        logger.debug("taint: could not stamp run %s: %s", run_id, exc)
