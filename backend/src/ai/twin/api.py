"""twin/api.py — the Scenario Shelf (TWIN T9).

Shelf CRUD, estimate, run, compare. Company-scoped on every path, and — the
one thing worth stating twice — **no endpoint accepts a grade** (§5.4). There
is no request model on this router with a `grade` field, and `TwinRun.grade` is
only ever written by the engine from what the run actually had. L6 says the
honesty layer is never softened; the cheapest guarantee is to give nobody a
way to soften it.

Two refusals here are deliberately *results* rather than errors:

* over the daily cap → the scenario **parks** and says "resumes tomorrow";
* an unacknowledged estimate → a 409 naming the price, not a silent run.

Both are §6's answer to charter decision 7 making twin spend visible.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.twin.grading import GRADE_DESCRIPTIONS, comparable
from src.ai.twin.materialise import Scope, ScopeRefused
from src.ai.twin.models import ScenarioKind, ScenarioStatus, TwinRun, TwinScenario
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/twin", tags=["Twin"])


class ScopeIn(BaseModel):
    objects: list[str] = Field(default_factory=list)
    window_days: Optional[int] = None


class ScenarioIn(BaseModel):
    name: str
    kind: str = ScenarioKind.CUSTOM
    levers: dict[str, Any] = Field(default_factory=dict)
    scope: ScopeIn = Field(default_factory=ScopeIn)
    # Deliberately absent: `grade`. See the module docstring.


def _scope_of(payload: ScopeIn) -> Scope:
    from src.common.config import settings

    return Scope(
        objects=tuple(payload.objects),
        window_days=payload.window_days or settings.TWIN_DEFAULT_WINDOW_DAYS,
    )


def _company_of(user: User) -> uuid.UUID:
    company_id = getattr(user, "company_id", None)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company on this session")
    return uuid.UUID(str(company_id))


async def _load_scenario(
    db: AsyncSession, scenario_id: uuid.UUID, company_id: uuid.UUID,
) -> TwinScenario:
    """Scope first, then act (the VG-05 rule).

    404 rather than 403 on a cross-tenant miss: a probe must not learn that an
    id exists in another tenant.
    """
    scenario = (await db.execute(
        select(TwinScenario).where(
            TwinScenario.id == scenario_id,
            TwinScenario.company_id == company_id,
        )
    )).scalar_one_or_none()
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario


@router.get("/scenarios")
async def list_scenarios(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    company_id = _company_of(user)
    rows = (await db.execute(
        select(TwinScenario)
        .where(TwinScenario.company_id == company_id,
               TwinScenario.status != ScenarioStatus.ARCHIVED)
        .order_by(TwinScenario.created_at.desc())
    )).scalars().all()
    return {
        "scenarios": [
            {
                "id": str(s.id), "name": s.name, "kind": s.kind,
                "scope": s.scope, "status": s.status,
                "acknowledged_estimate_usd": s.acknowledged_estimate_usd,
            }
            for s in rows
        ]
    }


@router.post("/scenarios", status_code=201)
async def create_scenario(
    payload: ScenarioIn,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    company_id = _company_of(user)
    scope = _scope_of(payload.scope)
    try:
        scope.validate()
    except ScopeRefused as exc:
        # 422, and the message says why the cap is a refusal rather than a
        # truncation — a caller who reads it learns the rule, not just the bound.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scenario = TwinScenario(
        company_id=company_id, name=payload.name, kind=payload.kind,
        levers=payload.levers,
        scope={"objects": list(scope.objects), "window_days": scope.window_days},
        created_by=getattr(user, "id", None),
    )
    db.add(scenario)
    await db.commit()
    await db.refresh(scenario)
    return {"id": str(scenario.id), "status": scenario.status}


@router.post("/scenarios/{scenario_id}/estimate")
async def estimate_scenario(
    scenario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Price it before it runs (§6.4).

    Acknowledging the estimate is what the run path checks — a tenant should
    never learn a what-if's price afterwards.
    """
    from src.ai.twin.cost import admit, estimate

    company_id = _company_of(user)
    scenario = await _load_scenario(db, scenario_id, company_id)
    scope = Scope(
        objects=tuple(scenario.scope.get("objects", [])),
        window_days=int(scenario.scope.get("window_days", 7)),
    )

    priced = await estimate(company_id, scope)
    cap = await admit(db, company_id, priced.usd)

    scenario.acknowledged_estimate_usd = priced.usd
    scenario.status = ScenarioStatus.READY
    await db.commit()

    return {
        "estimate": priced.as_dict(),
        "budget": {
            "admitted": cap.admitted,
            "parked": cap.parked,
            "reason": cap.reason,
            "spent_today_usd": round(cap.spent_usd, 4),
            "daily_cap_usd": cap.cap_usd,
        },
    }


@router.get("/scenarios/{scenario_id}/runs")
async def list_runs(
    scenario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    company_id = _company_of(user)
    await _load_scenario(db, scenario_id, company_id)
    rows = (await db.execute(
        select(TwinRun)
        .where(TwinRun.scenario_id == scenario_id)
        .order_by(TwinRun.started_at.desc())
    )).scalars().all()
    return {"runs": [_run_view(r) for r in rows]}


def _run_view(run: TwinRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "grade": run.grade,
        # The caveat travels with the number, everywhere the number goes.
        "grade_means": GRADE_DESCRIPTIONS.get(run.grade, ""),
        "method": run.method,
        "metrics": run.metrics,
        "cost_usd": run.cost_usd,
        "is_baseline": run.is_baseline,
        "refusal_reason": run.refusal_reason,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


class CompareIn(BaseModel):
    run_ids: list[uuid.UUID]
    metric: str


@router.post("/compare")
async def compare_runs(
    payload: CompareIn,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Compare N runs on one metric (§9's tournament).

    **Grades are compared, not averaged.** A tournament mixing a `replay`
    result with an `unknown` one shows both grades on the row and refuses to
    rank across them without the mismatch stated. Ranking a forecast above a
    replay because its number was bigger is the failure mode L6 exists to
    prevent, so the refusal is in the response body rather than left to a
    frontend to remember.
    """
    company_id = _company_of(user)
    rows = (await db.execute(
        select(TwinRun).where(
            TwinRun.id.in_(payload.run_ids),
            TwinRun.company_id == company_id,
        )
    )).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="No runs found")

    grades = {r.grade for r in rows}
    rankable = len(grades) == 1 and all(
        comparable(a.grade, b.grade) for a in rows for b in rows)

    entries = [
        {
            "run_id": str(r.id),
            "grade": r.grade,
            "grade_means": GRADE_DESCRIPTIONS.get(r.grade, ""),
            "value": (r.metrics or {}).get(payload.metric),
        }
        for r in rows
    ]

    return {
        "metric": payload.metric,
        "entries": entries,
        "ranked": rankable,
        "ranking_refused_because": None if rankable else (
            f"these runs carry different honesty grades ({', '.join(sorted(grades))}), "
            f"so they measure different kinds of thing. They are shown side by "
            f"side and deliberately not ranked — a bigger forecast is not a "
            f"better result than a smaller replay."
        ),
    }


async def _arq_pool() -> Any:
    """A short-lived arq pool, the shipped pattern (`ai/service.py`).
    Returns None when Redis is unreachable so the caller can say so
    rather than raise a connection error at the tenant."""
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        return await create_pool(RedisSettings())
    except Exception:  # noqa: BLE001 — an unreachable queue is a 503, not a 500
        logger.warning("twin: arq pool unavailable", exc_info=True)
        return None


@router.post("/scenarios/{scenario_id}/run", status_code=202)
async def run_scenario_endpoint(
    scenario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Queue a rehearsal (GLASS X3, decision 2).

    **Not a certified act**, deliberately: a scenario writes only to the
    twin plane and can reach nothing outside it (X1's binding), so the
    ceremony belongs at *promotion*, where a rehearsal becomes a real
    change — and there it is one of the two existing certified acts, never
    an eleventh (R5, 14_glass.md §6).

    The estimate must have been acknowledged first. That is not
    bureaucracy: twin spend is tenant-initiated (Inc-6 charter decision
    6), so a tenant learning a what-if's price *afterwards* is exactly the
    failure the estimate endpoint exists to prevent.
    """
    from src.ai.twin.jobs import enqueue_scenario_run

    company_id = _company_of(user)
    scenario = await _load_scenario(db, scenario_id, company_id)

    if scenario.acknowledged_estimate_usd is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Price this scenario before running it — a what-if should "
                "never cost money the owner has not seen first."
            ),
        )

    queued = await enqueue_scenario_run(await _arq_pool(), scenario_id)
    if not queued:
        raise HTTPException(
            status_code=503,
            detail=(
                "The rehearsal could not be queued — the worker is not "
                "reachable. Nothing was spent; try again shortly."
            ),
        )
    return {"scenario_id": str(scenario_id), "queued": True}


class PromoteIn(BaseModel):
    """What a rehearsal is being used to argue for."""

    entity_id: uuid.UUID
    field: str = Field(min_length=1, max_length=80)
    addition: str = Field(min_length=1, max_length=4000)


@router.post("/runs/{run_id}/promote", status_code=201)
async def promote_run(
    run_id: uuid.UUID,
    payload: PromoteIn,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Take a rehearsal to a human (GLASS X4, decision 3).

    **Not a new certified act.** This raises a HITL card on the existing
    ``before_self_evolving_code_promotion`` checkpoint; the human approves
    it through ``respond_to_approval``, which is already certified endpoint
    #1. The certified set stays ten (R5) — see 14_glass.md §6.

    ``propose_promotion``'s two refusals stand in front of this: a refused
    run has no result to argue from, and an ``unknown``-graded run is an
    illustration. Both answer 422 rather than raising a card, because
    putting an illustration in front of an owner as though it were
    evidence is how a ceremony stops meaning anything.
    """
    from src.ai.twin.promotion import EvidenceTooWeak, propose_promotion
    from src.ai.twin.promotion_chain import raise_promotion_approval

    company_id = _company_of(user)
    run = (await db.execute(
        select(TwinRun).where(
            TwinRun.id == run_id, TwinRun.company_id == company_id)
    )).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    try:
        evidence = await propose_promotion(db, run)
    except EvidenceTooWeak as weak:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(weak)) from weak

    approval = await raise_promotion_approval(
        db, company_id=company_id, entity_id=payload.entity_id,
        evidence=evidence, field=payload.field, addition=payload.addition)
    await db.commit()
    return {
        "approval_id": str(approval.id),
        "checkpoint_key": approval.checkpoint_key,
        "awaiting": "a human decision — nothing has changed yet",
    }
