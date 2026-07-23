"""Inc 5 / RTR v1 — the router reproduces the default, records a decision, and
the LLMRouter seam delegates when a company opts in (needs_db).

v1 is non-inferior by construction: it selects the *same* model the task default
points to, but now via the registry and with a committed ``routing_decisions``
row. This proves the audit trail + the delegation branch + the usage-log link,
without an LLM call (a stubbed adapter isolates the routing logic).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

import src.ai.orm  # noqa: F401 — register execution_runs/companies (RoutingDecision FK targets)
from src.auth.models import Company  # noqa: F401 — register the auth mapper
from src.ai.intelligence.catalog import ModelSpec, PriceSpec
from src.ai.intelligence.models import ModelStatus
from src.ai.intelligence.registry import RegistryService
from src.ai.intelligence.router import IntelligenceRouter
from src.ai.intelligence.types import RoutingSignals
from src.common.security import encrypt_api_key

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

_PROV = "testprovrtr"


def _spec() -> ModelSpec:
    return ModelSpec(
        model_key=f"{_PROV}-m", provider=_PROV, model_name="m-router", version="1", region="us",
        capability_profile={"reasoning_strength": 0.8, "tool_reliability": 0.8,
                            "max_context": 100000, "latency_class": "standard",
                            "modalities": ["text"], "supports_tools": True},
        data_flow={"data_region": "us", "subprocessor": "t",
                   "trains_on_customer_data": False, "default_allowed": True},
        status=ModelStatus.ACTIVE, prices=(PriceSpec("input_token", Decimal("0.001")),),
    )


@pytest_asyncio.fixture
async def setup():
    import os
    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine
    await engine.dispose()

    cid = uuid.uuid4()
    ir_id = uuid.uuid4()
    sku = f"{_PROV}-sku-{cid.hex[:6]}"

    async with AsyncSessionLocal() as s:
        await s.execute(text(
            "INSERT INTO companies (id, name, type, status, created_at, updated_at) "
            "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"rtr-{cid.hex[:8]}"})
        cat_id = None
        await RegistryService(s).install_model_catalog([_spec()])
        cat_id = (await s.execute(text(
            "SELECT id FROM model_registry WHERE provider = :p"), {"p": _PROV})).scalar()
        # An integration BOUND to the catalog row, with a (fake) encrypted key.
        await s.execute(text(
            "INSERT INTO integration_registry (id, company_id, provider_name, model_name, "
            "service_sku, service_category, component_type, encrypted_api_key, internal_cost, "
            "cost_unit, status, model_registry_id, created_at, updated_at) VALUES "
            "(:id, :c, :p, 'm-router', :sku, 'LLM', 'input_token', :key, 0.001, '1k tokens', "
            "'active', :cat, now(), now())"),
            {"id": str(ir_id), "c": str(cid), "p": _PROV, "sku": sku,
             "key": encrypt_api_key("fake-key"), "cat": str(cat_id)})
        # Two task defaults over the same integration: one routed, one single.
        for task_type, mode in (("text_generation", "router"), ("thinking", "single")):
            await s.execute(text(
                "INSERT INTO model_task_defaults (id, company_id, task_type, integration_id, "
                "routing_mode, is_default, created_at, updated_at) VALUES "
                "(:id, :c, :t, :ir, :mode, true, now(), now())"),
                {"id": str(uuid.uuid4()), "c": str(cid), "t": task_type, "ir": str(ir_id), "mode": mode})
        await s.commit()

    try:
        yield cid, ir_id, uuid.UUID(str(cat_id)), sku
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM usage_logs WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM routing_decisions WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM model_task_defaults WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM integration_registry WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text(
                "DELETE FROM model_prices WHERE model_registry_id IN "
                "(SELECT id FROM model_registry WHERE provider = :p)"), {"p": _PROV})
            await s.execute(text("DELETE FROM model_registry WHERE provider = :p"), {"p": _PROV})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


async def test_route_selects_the_bound_model_and_records_decision(setup):
    from src.common.database import AsyncSessionLocal
    cid, ir_id, cat_id, sku = setup

    async with AsyncSessionLocal() as db:
        binding = await IntelligenceRouter(db, cid).route(RoutingSignals(task_type="text_generation"))

    # One catalog-bound candidate → v2 scores it (reason "auto") and selects that
    # same model: the company's credentialed, bound integration.
    assert binding.integration_id == ir_id
    assert binding.model_name == "m-router"
    assert binding.model_registry_id == cat_id
    assert binding.reason == "auto"
    assert binding.decision_id is not None

    # A decision was committed (its own transaction) — the audit trail.
    async with AsyncSessionLocal() as db:
        row = (await db.execute(text(
            "SELECT task_type, model_registry_id, reason, fallback_used FROM routing_decisions "
            "WHERE id = :d"), {"d": str(binding.decision_id)})).one()
    assert row.task_type == "text_generation"
    assert uuid.UUID(str(row.model_registry_id)) == cat_id
    assert row.reason == "auto"
    assert row.fallback_used is False


async def test_llmrouter_delegates_only_in_router_mode(setup, monkeypatch):
    from src.common.database import AsyncSessionLocal
    import src.ai.llm.router as router_mod
    from src.ai.llm.router import LLMRouter
    cid, ir_id, cat_id, sku = setup

    # Stub adapter construction so we exercise the delegation branch without a
    # provider client or an LLM call.
    monkeypatch.setattr(router_mod, "_get_adapter", lambda **kw: object())

    async with AsyncSessionLocal() as db:
        r = LLMRouter(db, cid)
        # Routed task → a decision is recorded and stamped as pending.
        await r._resolve_adapter("text_generation")
        assert r._pending_decision_id is not None
        routed_id = r._pending_decision_id
        # Single-mode task → no routing, nothing stamped.
        await r._resolve_adapter("thinking")
        assert r._pending_decision_id is None

    async with AsyncSessionLocal() as db:
        n = (await db.execute(text(
            "SELECT count(*) FROM routing_decisions WHERE company_id = :c"), {"c": str(cid)})).scalar()
    assert n == 1  # exactly the one routed call recorded a decision
    assert routed_id is not None


async def test_usage_line_links_to_routing_decision(setup):
    from src.common.database import AsyncSessionLocal
    from src.ai.usage_service import UsageService
    cid, ir_id, cat_id, sku = setup

    # Record a decision, then log usage carrying its id → the FK link is set.
    async with AsyncSessionLocal() as db:
        binding = await IntelligenceRouter(db, cid).route(RoutingSignals(task_type="text_generation"))

    async with AsyncSessionLocal() as db:
        log = await UsageService(db).log_usage(
            company_id=cid, service_sku=sku, raw_quantity=1000.0,
            attribution="tool", routing_decision_id=binding.decision_id)
    assert log is not None
    assert log.routing_decision_id == binding.decision_id
