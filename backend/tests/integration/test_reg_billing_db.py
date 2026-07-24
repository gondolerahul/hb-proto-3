"""Inc 5 / REG T4 — backfill + the parity-safe billing reproducibility snapshot.

Proves: (1) an existing IntegrationRegistry row binds to its catalog row by
(provider, model_name), an unknown model stays NULL; (2) a *bound* integration's
usage row is stamped with the model + applied price (reproducible + version-
attributed) while the charge is unchanged; (3) an *un-bound* row's metadata is
passed through untouched (the billing/parity path does not move).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.auth.models import Company  # noqa: F401 — register the auth mapper
from src.ai.intelligence.catalog import ModelSpec, PriceSpec
from src.ai.intelligence.models import ModelStatus
from src.ai.intelligence.registry import RegistryService
from src.ai.usage_service import UsageService

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

_PROV = "testprovbill"


def _spec(model_name: str) -> ModelSpec:
    return ModelSpec(
        model_key=f"{_PROV}-{model_name}", provider=_PROV, model_name=model_name,
        version="1", region="us",
        capability_profile={"reasoning_strength": 0.8, "tool_reliability": 0.8,
                            "max_context": 100000, "latency_class": "standard",
                            "modalities": ["text"], "supports_tools": True},
        data_flow={"data_region": "us", "subprocessor": "t",
                   "trains_on_customer_data": False, "default_allowed": True},
        status=ModelStatus.ACTIVE,
        prices=(PriceSpec("input_token", Decimal("0.002")),),
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
    bound_sku = f"{_PROV}-bound-{cid.hex[:6]}"
    unbound_sku = f"{_PROV}-unbound-{cid.hex[:6]}"

    async with AsyncSessionLocal() as s:
        await s.execute(text(
            "INSERT INTO companies (id, name, type, status, created_at, updated_at) "
            "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"reg-bill-{cid.hex[:8]}"})
        # A model that IS in the catalog (will bind) + one that is NOT (stays NULL).
        await RegistryService(s).install_model_catalog([_spec("m-bill")])
        for sku, model in ((bound_sku, "m-bill"), (unbound_sku, "unknown-x")):
            await s.execute(text(
                "INSERT INTO integration_registry (id, company_id, provider_name, model_name, "
                "service_sku, service_category, component_type, internal_cost, cost_unit, status, "
                "created_at, updated_at) VALUES (:id, :c, :p, :m, :sku, 'LLM', 'input_token', "
                "0.002, '1k tokens', 'active', now(), now())"),
                {"id": str(uuid.uuid4()), "c": str(cid), "p": _PROV, "m": model, "sku": sku})
        await s.commit()

    try:
        yield cid, bound_sku, unbound_sku
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM usage_logs WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM integration_registry WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text(
                "DELETE FROM model_prices WHERE model_registry_id IN "
                "(SELECT id FROM model_registry WHERE provider = :p)"), {"p": _PROV})
            await s.execute(text("DELETE FROM model_registry WHERE provider = :p"), {"p": _PROV})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


async def test_backfill_binds_known_model_leaves_unknown_null(setup):
    from src.common.database import AsyncSessionLocal
    cid, bound_sku, unbound_sku = setup

    async with AsyncSessionLocal() as db:
        await RegistryService(db).backfill_integration_bindings()

    async with AsyncSessionLocal() as db:
        bound = (await db.execute(text(
            "SELECT model_registry_id FROM integration_registry WHERE service_sku = :s"),
            {"s": bound_sku})).scalar()
        unbound = (await db.execute(text(
            "SELECT model_registry_id FROM integration_registry WHERE service_sku = :s"),
            {"s": unbound_sku})).scalar()
    assert bound is not None, "known (provider, model_name) should have bound"
    assert unbound is None, "unknown model must stay un-bound (ops reconciles)"


async def test_bound_usage_is_stamped_unbound_is_untouched(setup):
    from src.common.database import AsyncSessionLocal
    cid, bound_sku, unbound_sku = setup

    async with AsyncSessionLocal() as db:
        await RegistryService(db).backfill_integration_bindings()

    # Bound integration → the usage row carries the model + applied price, and
    # the charge is exactly internal_cost×qty/divisor (unchanged).
    async with AsyncSessionLocal() as db:
        log = await UsageService(db).log_usage(
            company_id=cid, service_sku=bound_sku, raw_quantity=1000.0,
            metadata={"k": "v"}, attribution="tool")
    assert log is not None
    assert log.calculated_cost == Decimal("0.002000")  # 0.002 × 1000 / 1000
    binding = log.log_metadata["model_binding"]
    assert Decimal(binding["applied_unit_price"]) == Decimal("0.002")  # Numeric(18,6) → "0.002000"
    assert binding["cost_unit"] == "1k tokens"
    assert uuid.UUID(binding["model_registry_id"])       # a real catalog id
    assert log.log_metadata["k"] == "v"                  # caller metadata preserved

    # Un-bound integration → metadata passed through byte-identical (None stays None).
    async with AsyncSessionLocal() as db:
        log2 = await UsageService(db).log_usage(
            company_id=cid, service_sku=unbound_sku, raw_quantity=1000.0,
            metadata=None, attribution="tool")
    assert log2 is not None
    assert log2.log_metadata is None                     # the billing path did not move
