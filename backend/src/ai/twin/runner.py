"""twin/runner.py — the assembly (GLASS X2).

TWIN's honest limit, in its own words: *"No scenario runner is wired
end-to-end… the pieces are each tested, the assembly is not, and calling
it done would be the dishonest version of this row."* This module is that
assembly — the thing that turns a scenario into a real ``TwinRun`` row
written from a real replay.

The order is deliberate and each step earns its place:

1. **Admit** against the daily Glasshouse cap (``cost.admit``).
2. **Estimate**, then check affordability **for the whole scenario** before
   spending anything — decision 4's actual intent: refuse before spending,
   not half-way through.
3. **Materialise** the twin plane. Deliberately *outside* any binding: this
   is the one legitimate live-plane read in the package, and a materialiser
   that read the twin plane would copy an empty schema over itself, failing
   as "the scenario found nothing".
4. **Substitute** — build the run's tool set from the company's real tools.
5. **Replay** through a handler that spawns a twin ``ExecutionRun`` per
   signal and executes the **shipped** agent loop inside ``twin_bound``.
6. **Grade** from what the engine observed, never from what anyone wants.
7. **Write** the ``TwinRun``; settle every hold.

**Refusals are results, not exceptions** (TWIN's precedent): over the cap,
unaffordable, scope refused — each writes a ``TwinRun`` carrying its
``refusal_reason``, so the Scenario Shelf can say *why* a rehearsal did
not happen instead of showing a gap.

**Holds are per replayed run, gated by an up-front affordability check.**
``WalletHold.run_id`` is FK'd to ``execution_runs`` and unique, so a
single scenario-level hold would have needed an invented anchor run with
an arbitrarily chosen entity. Per-run holds through the shipped path are
both truer (a rehearsal is admitted the way real work is admitted) and
free of that invention; the up-front check is what keeps the promise that
an unaffordable scenario refuses before it spends.

**External effects must be zero, and that is asserted.** A run finishing
with ``external_effects > 0`` is written as a *failed* run with a refusal
reason: it means substitution did not hold, and saying so loudly beats
publishing a tidy result.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.twin.binding import TwinBinding, twin_bound
from src.ai.twin.grading import Grade, GradeInputs, grade
from src.ai.twin.materialise import Scope, ScopeRefused, materialise
from src.ai.twin.models import TwinRun
from src.ai.twin.replay import replay
from src.ai.twin.substitution import CallRecorder, substituted_registry

logger = logging.getLogger(__name__)

__all__ = ["ScenarioOutcome", "run_scenario", "SIMULATION_LEAKED"]

#: The refusal a leaked external effect earns. Named so a test can assert
#: on the constant rather than on prose that may be reworded.
SIMULATION_LEAKED = (
    "This rehearsal reached the outside world, so its result cannot be "
    "trusted and has not been kept. Substitution did not hold."
)

#: What one replayed signal is allowed to reserve. A rehearsal of a
#: PROCESS's work is admitted like a PROCESS's work.
REPLAY_ENTITY_TYPE = "PROCESS"


@dataclass
class ScenarioOutcome:
    run: TwinRun
    refused: bool

    @property
    def grade(self) -> str:
        return self.run.grade


async def _refusal(
    db: AsyncSession, scenario: Any, reason: str, *, now: datetime,
) -> ScenarioOutcome:
    """A refusal is a row, not an exception — the shelf must be able to say
    why a rehearsal did not happen."""
    run = TwinRun(
        company_id=scenario.company_id,
        scenario_id=scenario.id,
        grade=Grade.UNKNOWN,
        method=None,
        metrics={},
        cost_usd=0.0,
        refusal_reason=reason,
        started_at=now,
        finished_at=datetime.utcnow(),
    )
    db.add(run)
    await db.commit()
    return ScenarioOutcome(run=run, refused=True)


async def _spawn_twin_run(
    db: AsyncSession, company_id: uuid.UUID, signal: Any, entity_id: uuid.UUID,
) -> Any:
    """The control-plane row a rehearsed signal executes as.

    A real ``ExecutionRun``, deliberately: a rehearsal that left no audit
    trail would be the one kind of work in this platform nobody could look
    at afterwards. ``input_data.twin`` marks it so a reader never mistakes
    it for something that happened.
    """
    from src.ai.orm.execution import ExecutionRun
    from src.ai.schemas.enums import RunStatus

    run = ExecutionRun(
        company_id=company_id,
        entity_id=entity_id,
        input_data={
            "input": f"[glasshouse] rehearse {signal.type}",
            "channel": "twin",
            "event_type": signal.type,
            "signal_id": str(signal.id),
            "twin": True,
        },
        status=RunStatus.PENDING,
    )
    db.add(run)
    await db.flush()
    return run


async def _default_execute(db: AsyncSession, redis: Any, run_id: uuid.UUID) -> None:
    """Run the **shipped** loop. Injectable so tests drive the assembly
    deterministically without standing up an LLM — the TWIN precedent for
    every injected seam in this package."""
    from src.ai.core.agent_loop import AgentLoop

    await AgentLoop(db, redis).run(run_id)


async def run_scenario(
    db: AsyncSession,
    scenario: Any,
    *,
    redis: Any = None,
    now: Optional[datetime] = None,
    execute: Optional[Callable[[AsyncSession, Any, uuid.UUID], Awaitable[None]]] = None,
    signal_limit: int = 500,
) -> ScenarioOutcome:
    """Rehearse one scenario end to end. Commits. Never raises for a
    refusal — only for a genuine fault."""
    from src.ai.loop.wallet_holds import (
        available_for_spend,
        place_hold,
        settle_hold,
    )
    from src.ai.signals.models import Signal
    from src.ai.signals.triggers import resolve_owner
    from src.ai.tools.base import ToolRegistry
    from src.ai.twin import cost as cost_module

    now = now or datetime.utcnow()
    company_id = scenario.company_id
    execute = execute or _default_execute

    scope = Scope(
        objects=tuple((scenario.scope or {}).get("objects", ()) or ()),
        window_days=int(
            (scenario.scope or {}).get("window_days")
            or Scope().window_days),
    )
    try:
        scope.validate()
    except ScopeRefused as refused:
        return await _refusal(db, scenario, str(refused), now=now)

    # 1 — price it. Both gates below need the number, so it comes first.
    estimate = await cost_module.estimate(company_id, scope)

    # 2 — the daily Glasshouse cap, then the wallet. Two different refusals
    # on purpose: over the cap the scenario "resumes tomorrow, nothing is
    # lost"; out of credit is a different sentence for a different fix.
    decision = await cost_module.admit(db, company_id, estimate.usd)
    if not decision.admitted:
        return await _refusal(db, scenario, decision.reason, now=now)

    available = await available_for_spend(db, company_id)
    if Decimal(str(estimate.usd)) > available:
        return await _refusal(
            db, scenario,
            f"This rehearsal is priced at about ${estimate.usd:.2f} and the "
            f"wallet has ${available:.2f} available. Nothing was spent.",
            now=now)

    # 3 — stand the room up. Outside any binding, on purpose.
    try:
        await materialise(company_id, scope)
    except ScopeRefused as refused:
        return await _refusal(db, scenario, str(refused), now=now)

    # 4 — the tools this run may reach.
    recorder = CallRecorder()
    binding = TwinBinding(
        company_id=company_id,
        tools=substituted_registry(
            ToolRegistry.get_tools_for_company(company_id), recorder),
        recorder=recorder,
    )

    spent = Decimal("0")
    executed_runs: list[uuid.UUID] = []

    async def handler(signal_id: uuid.UUID) -> None:
        """One rehearsed signal: resolve its owner exactly as the shipped
        dispatcher does, spawn a twin run, execute the shipped loop inside
        the binding, settle."""
        nonlocal spent
        signal = await db.get(Signal, signal_id)
        if signal is None:
            return
        owner = await resolve_owner(db, company_id, signal.type)
        if owner is None:
            # Parked in life, skipped in rehearsal — and counted by neither.
            return
        run = await _spawn_twin_run(
            db, company_id, signal, owner.process_entity_id)
        await place_hold(
            db, company_id, run.id, REPLAY_ENTITY_TYPE,
            Decimal(str(cost_module.USD_PER_REPLAYED_SIGNAL)))
        await db.commit()
        try:
            with twin_bound(binding):
                await execute(db, redis, run.id)
        finally:
            actual = Decimal(str(getattr(run, "total_cost_usd", 0) or 0))
            spent += actual
            await settle_hold(db, run.id, actual)
            await db.commit()
        executed_runs.append(run.id)

    # 5 — the replay itself. TWIN selects and counts; this drives.
    result = await replay(
        db, company_id, scope, handler=handler, limit=signal_limit)

    # 6 — the leak assertion. Louder than a tidy result.
    if result.external_effects > 0:
        logger.error(
            "[twin] scenario %s leaked %d external effect(s)",
            scenario.id, result.external_effects)
        return await _refusal(db, scenario, SIMULATION_LEAKED, now=now)

    # 7 — grade from what the engine observed.
    computed = grade(GradeInputs(
        replayed_signals=result.signals_replayed,
        series_points=0,
        real_code_path=True,
        unobserved_levers=bool((scenario.levers or {}).get("unobserved")),
    ))

    run = TwinRun(
        company_id=company_id,
        scenario_id=scenario.id,
        grade=computed,
        method=(
            f"replayed {result.signals_replayed} signal(s) through the "
            f"shipped loop with every external tool substituted"
        ),
        metrics={
            "signals_replayed": result.signals_replayed,
            "runs_executed": len(executed_runs),
            "simulated_calls": result.simulated_calls,
            "external_effects": result.external_effects,
            "by_category": result.by_category,
            "truncated": result.truncated,
            "estimate_usd": round(estimate.usd, 4),
        },
        cost_usd=float(spent),
        started_at=now,
        finished_at=datetime.utcnow(),
    )
    db.add(run)
    await db.commit()
    return ScenarioOutcome(run=run, refused=False)
