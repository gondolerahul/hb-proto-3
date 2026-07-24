"""Inc 5 / EVX — the admission gate lives in the mutation path (needs_db).

The load-bearing check (design §8): a catalog model flips to ACTIVE **only**
through ``RegistryService.activate``, which refuses on a failed admission and
raises on a violated independent-suite rule. Plus the canary primitives:
watch flags a regressing routed cohort, roll_back reverts to preview.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

import src.ai.orm  # noqa: F401 — register execution_runs/companies (FK targets)
from src.auth.models import Company  # noqa: F401
from src.ai.intelligence import canary
from src.ai.intelligence.admission import AdmissionError
from src.ai.intelligence.catalog import ModelSpec, PriceSpec
from src.ai.intelligence.models import ModelStatus
from src.ai.intelligence.registry import RegistryService
from tests.eval.routing_corpus import (
    EXPENSIVE_CANDIDATE, FULL_SUITES, GOOD_CANDIDATE, INCUMBENT_EVAL,
    REGRESSED_CANDIDATE, SELF_GENERATED_ONLY,
)

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

_PROV = "testprovevx"


def _spec(status: str) -> ModelSpec:
    return ModelSpec(
        model_key=f"{_PROV}-m", provider=_PROV, model_name="m-evx", version="1", region="us",
        capability_profile={"reasoning_strength": 0.8, "tool_reliability": 0.8, "max_context": 100000,
                            "latency_class": "standard", "modalities": ["text"], "supports_tools": True},
        data_flow={"data_region": "us", "subprocessor": "t",
                   "trains_on_customer_data": False, "default_allowed": False},
        status=status, prices=(PriceSpec("input_token", Decimal("0.001")),),
    )


async def _model_status(model_id) -> str:
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        return (await s.execute(text(
            "SELECT status FROM model_registry WHERE id = :m"), {"m": str(model_id)})).scalar()


async def _admission_signal(model_id):
    """The most recent admission signal's 'admitted' flag ('true'/'false'/None)."""
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        return (await s.execute(text(
            "SELECT payload->>'admitted' FROM signals WHERE type = 'model.admission_evaluated' "
            "AND payload->>'model_registry_id' = :m ORDER BY created_at DESC LIMIT 1"),
            {"m": str(model_id)})).scalar()


@pytest_asyncio.fixture
async def preview_model():
    import os
    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine
    await engine.dispose()

    async with AsyncSessionLocal() as s:
        await RegistryService(s).install_model_catalog([_spec(ModelStatus.PREVIEW)])
        mid = (await s.execute(text(
            "SELECT id FROM model_registry WHERE provider = :p"), {"p": _PROV})).scalar()
    try:
        yield uuid.UUID(str(mid))
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text(
                "DELETE FROM signals WHERE payload->>'model_registry_id' = :m"), {"m": str(mid)})
            await s.execute(text(
                "DELETE FROM model_prices WHERE model_registry_id IN "
                "(SELECT id FROM model_registry WHERE provider = :p)"), {"p": _PROV})
            await s.execute(text("DELETE FROM model_registry WHERE provider = :p"), {"p": _PROV})
            await s.commit()


async def test_good_candidate_is_admitted_and_the_model_activates(preview_model):
    from src.common.database import AsyncSessionLocal
    mid = preview_model
    async with AsyncSessionLocal() as db:
        result = await RegistryService(db).activate(
            mid, candidate=GOOD_CANDIDATE, incumbent=INCUMBENT_EVAL,
            suites=FULL_SUITES, task_classes=("drafting",))
    assert result.admitted is True
    assert await _model_status(mid) == ModelStatus.ACTIVE      # the flip happened
    assert await _admission_signal(mid) == "true"              # audited


async def test_regressed_candidate_is_refused_and_the_model_stays_preview(preview_model):
    from src.common.database import AsyncSessionLocal
    mid = preview_model
    async with AsyncSessionLocal() as db:
        result = await RegistryService(db).activate(
            mid, candidate=REGRESSED_CANDIDATE, incumbent=INCUMBENT_EVAL, suites=FULL_SUITES)
    assert result.admitted is False
    assert result.quality_ok is False
    assert await _model_status(mid) == ModelStatus.PREVIEW     # router preference cannot override
    assert await _admission_signal(mid) == "false"            # the refusal is audited


async def test_over_budget_candidate_is_refused(preview_model):
    from src.common.database import AsyncSessionLocal
    mid = preview_model
    async with AsyncSessionLocal() as db:
        result = await RegistryService(db).activate(
            mid, candidate=EXPENSIVE_CANDIDATE, incumbent=INCUMBENT_EVAL, suites=FULL_SUITES)
    assert result.admitted is False and result.cost_ok is False
    assert await _model_status(mid) == ModelStatus.PREVIEW


async def test_self_generated_only_suites_raise_and_never_activate(preview_model):
    from src.common.database import AsyncSessionLocal
    mid = preview_model
    with pytest.raises(AdmissionError):
        async with AsyncSessionLocal() as db:
            await RegistryService(db).activate(
                mid, candidate=GOOD_CANDIDATE, incumbent=INCUMBENT_EVAL, suites=SELF_GENERATED_ONLY)
    assert await _model_status(mid) == ModelStatus.PREVIEW     # the exam must predate the student


async def test_canary_rollback_reverts_active_to_preview(preview_model):
    from src.common.database import AsyncSessionLocal
    mid = preview_model
    # First admit it (→ active), then a bad canary rolls it back.
    async with AsyncSessionLocal() as db:
        await RegistryService(db).activate(
            mid, candidate=GOOD_CANDIDATE, incumbent=INCUMBENT_EVAL, suites=FULL_SUITES)
    assert await _model_status(mid) == ModelStatus.ACTIVE

    async with AsyncSessionLocal() as db:
        await canary.roll_back(db, mid)
    assert await _model_status(mid) == ModelStatus.PREVIEW     # dropped from candidates
    async with AsyncSessionLocal() as db:
        rolled = (await db.execute(text(
            "SELECT count(*) FROM signals WHERE type = 'model.canary_rolled_back' "
            "AND payload->>'model_registry_id' = :m"), {"m": str(mid)})).scalar()
    assert rolled == 1


async def test_canary_watch_flags_a_high_fallback_cohort():
    import os
    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine
    await engine.dispose()   # reset the pool for this test's loop (asyncpg, HANDOFF §5)
    cid = uuid.uuid4()
    since = datetime.utcnow() - timedelta(minutes=1)
    async with AsyncSessionLocal() as s:
        await s.execute(text(
            "INSERT INTO companies (id, name, type, status, created_at, updated_at) "
            "VALUES (:id, :n, 'TENANT', 'active', now(), now())"), {"id": str(cid), "n": f"evx-{cid.hex[:8]}"})
        # 10 decisions, 4 of them fallbacks → 40% fallback rate (> 20% threshold).
        for i in range(10):
            await s.execute(text(
                "INSERT INTO routing_decisions (id, company_id, task_type, reason, signals, "
                "fallback_used, created_at) VALUES (:id, :c, 'text_generation', :r, '{}'::jsonb, :fb, now())"),
                {"id": str(uuid.uuid4()), "c": str(cid), "r": ("fallback" if i < 4 else "auto"),
                 "fb": (i < 4)})
        await s.commit()
    try:
        async with AsyncSessionLocal() as db:
            verdict = await canary.watch(db, since=since)
        assert verdict.samples >= 10
        assert verdict.fallback_rate >= 0.4
        assert verdict.healthy is False   # a regressing cohort → rollback
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM routing_decisions WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
