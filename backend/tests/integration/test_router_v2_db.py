"""Inc 5 / RTR v2 — scored selection + downshift + safe fallback (needs_db).

Candidates are the company's own credentialed, catalog-bound models. On a hard
step (``thinking``, complexity 0.85): at neutral wallet the capable model wins
('auto'); with an empty wallet the same step downshifts to the cheaper model
('downshift'); a company with no catalog-bound model falls back to its configured
default ('rule') — router mode is always safe.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

import src.ai.orm  # noqa: F401 — register execution_runs/companies (RoutingDecision FKs)
from src.auth.models import Company  # noqa: F401
from src.ai.intelligence.catalog import ModelSpec, PriceSpec
from src.ai.intelligence.models import ModelStatus
from src.ai.intelligence.registry import RegistryService
from src.ai.intelligence.router import IntelligenceRouter
from src.ai.intelligence.types import RoutingSignals
from src.common.security import encrypt_api_key

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

_PROV = "testprovv2"


def _spec(name: str, reasoning: float, inp: str, outp: str) -> ModelSpec:
    return ModelSpec(
        model_key=f"{_PROV}-{name}", provider=_PROV, model_name=name, version="1", region="us",
        capability_profile={"reasoning_strength": reasoning, "tool_reliability": 0.9,
                            "max_context": 200000, "latency_class": "standard",
                            "modalities": ["text"], "supports_tools": True},
        data_flow={"data_region": "us", "subprocessor": "t",
                   "trains_on_customer_data": False, "default_allowed": True},
        status=ModelStatus.ACTIVE,
        prices=(PriceSpec("input_token", Decimal(inp)), PriceSpec("output_token", Decimal(outp))),
    )


async def _mk_ir(s, cid, model_name, sku, cat_id):
    await s.execute(text(
        "INSERT INTO integration_registry (id, company_id, provider_name, model_name, service_sku, "
        "service_category, component_type, encrypted_api_key, internal_cost, cost_unit, status, "
        "model_registry_id, created_at, updated_at) VALUES (:id, :c, :p, :m, :sku, 'LLM', "
        "'input_token', :key, 0.001, '1k tokens', 'active', :cat, now(), now())"),
        {"id": str(uuid.uuid4()), "c": str(cid), "p": _PROV, "m": model_name, "sku": sku,
         "key": encrypt_api_key("k"), "cat": (str(cat_id) if cat_id else None)})


async def _cleanup(cid):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        await s.execute(text("DELETE FROM routing_decisions WHERE company_id = :c"), {"c": str(cid)})
        await s.execute(text("DELETE FROM model_task_defaults WHERE company_id = :c"), {"c": str(cid)})
        await s.execute(text("DELETE FROM integration_registry WHERE company_id = :c"), {"c": str(cid)})
        await s.execute(text(
            "DELETE FROM model_prices WHERE model_registry_id IN "
            "(SELECT id FROM model_registry WHERE provider = :p)"), {"p": _PROV})
        await s.execute(text("DELETE FROM model_registry WHERE provider = :p"), {"p": _PROV})
        await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
        await s.commit()


@pytest_asyncio.fixture
async def two_models():
    import os
    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine
    await engine.dispose()

    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(text(
            "INSERT INTO companies (id, name, type, status, created_at, updated_at) "
            "VALUES (:id, :n, 'TENANT', 'active', now(), now())"), {"id": str(cid), "n": f"v2-{cid.hex[:8]}"})
        await RegistryService(s).install_model_catalog([
            _spec("cap", 0.95, "0.015", "0.075"),     # capable, expensive (cost_proxy 0.09)
            _spec("cheap", 0.55, "0.001", "0.004"),   # weak, cheap (cost_proxy 0.005)
        ])
        cap_id = (await s.execute(text(
            "SELECT id FROM model_registry WHERE provider = :p AND model_name = 'cap'"), {"p": _PROV})).scalar()
        cheap_id = (await s.execute(text(
            "SELECT id FROM model_registry WHERE provider = :p AND model_name = 'cheap'"), {"p": _PROV})).scalar()
        await _mk_ir(s, cid, "cap", f"{_PROV}-cap-{cid.hex[:6]}", cap_id)
        await _mk_ir(s, cid, "cheap", f"{_PROV}-cheap-{cid.hex[:6]}", cheap_id)
        await s.commit()
    try:
        yield cid
    finally:
        await _cleanup(cid)


async def test_neutral_wallet_routes_to_the_capable_model(two_models):
    from src.common.database import AsyncSessionLocal
    cid = two_models
    async with AsyncSessionLocal() as db:
        binding = await IntelligenceRouter(db, cid).route(RoutingSignals(task_type="thinking"))
    # No envelope → neutral pressure → capability wins on a hard step.
    assert binding.model_name == "cap"
    assert binding.reason == "auto"
    # The decision snapshot carries the computed complexity (audit legibility).
    async with AsyncSessionLocal() as db:
        sig = (await db.execute(text(
            "SELECT signals FROM routing_decisions WHERE id = :d"), {"d": str(binding.decision_id)})).scalar()
    assert sig["complexity"] >= 0.8  # "thinking" prior


async def test_empty_wallet_downshifts_to_the_cheaper_model(two_models):
    from src.common.database import AsyncSessionLocal
    cid = two_models
    async with AsyncSessionLocal() as db:
        # _select with an empty wallet (inject headroom; route() would read it from
        # the envelope, exercised separately) — the same hard step downshifts.
        iid, model_name, provider, mrid, reason = await IntelligenceRouter(db, cid)._select(
            RoutingSignals(task_type="thinking", complexity=0.85, wallet_headroom_usd=0.0))
    assert model_name == "cheap"
    assert reason == "downshift"


async def test_wallet_headroom_is_none_without_an_envelope(two_models):
    from src.common.database import AsyncSessionLocal
    cid = two_models
    async with AsyncSessionLocal() as db:
        headroom = await IntelligenceRouter(db, cid)._wallet_headroom()
    assert headroom is None   # → neutral cost pressure


async def test_reroute_picks_next_best_excluding_the_failed_model(two_models):
    from src.common.database import AsyncSessionLocal
    cid = two_models
    async with AsyncSessionLocal() as db:
        b = await IntelligenceRouter(db, cid).reroute(
            RoutingSignals(task_type="thinking"), exclude={"cap"})
    assert b is not None
    assert b.model_name == "cheap"          # the only remaining candidate
    assert b.reason == "fallback"
    async with AsyncSessionLocal() as db:
        row = (await db.execute(text(
            "SELECT reason, fallback_used FROM routing_decisions WHERE id = :d"),
            {"d": str(b.decision_id)})).one()
    assert row.reason == "fallback"
    assert row.fallback_used is True


async def test_reroute_returns_none_when_no_alternative_remains(two_models):
    from src.common.database import AsyncSessionLocal
    cid = two_models
    async with AsyncSessionLocal() as db:
        b = await IntelligenceRouter(db, cid).reroute(
            RoutingSignals(task_type="thinking"), exclude={"cap", "cheap"})
    assert b is None   # everything tried → the caller re-raises the provider error


async def test_company_with_no_bound_model_falls_back_to_default():
    """An un-bound integration has no catalog candidate → the router reproduces
    the configured task default (reason 'rule') — router mode is always safe."""
    import os
    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine
    await engine.dispose()

    cid = uuid.uuid4()
    ir_id = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(text(
            "INSERT INTO companies (id, name, type, status, created_at, updated_at) "
            "VALUES (:id, :n, 'TENANT', 'active', now(), now())"), {"id": str(cid), "n": f"v2u-{cid.hex[:8]}"})
        await s.execute(text(
            "INSERT INTO integration_registry (id, company_id, provider_name, model_name, service_sku, "
            "service_category, component_type, internal_cost, cost_unit, status, created_at, updated_at) "
            "VALUES (:id, :c, :p, 'legacy-model', :sku, 'LLM', 'input_token', 0.001, '1k tokens', "
            "'active', now(), now())"),  # model_registry_id left NULL — un-bound
            {"id": str(ir_id), "c": str(cid), "p": _PROV, "sku": f"{_PROV}-legacy-{cid.hex[:6]}"})
        await s.execute(text(
            "INSERT INTO model_task_defaults (id, company_id, task_type, integration_id, routing_mode, "
            "is_default, created_at, updated_at) VALUES (:id, :c, 'thinking', :ir, 'router', true, now(), now())"),
            {"id": str(uuid.uuid4()), "c": str(cid), "ir": str(ir_id)})
        await s.commit()
    try:
        async with AsyncSessionLocal() as db:
            iid, model_name, provider, mrid, reason = await IntelligenceRouter(db, cid)._select(
                RoutingSignals(task_type="thinking", complexity=0.85))
        assert model_name == "legacy-model"
        assert reason == "rule"       # the safe v1 fallback
        assert mrid is None           # un-bound
    finally:
        await _cleanup(cid)
