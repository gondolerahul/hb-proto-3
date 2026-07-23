"""Inc 5 / FLEET — the D5 allow-list actually gates routing (needs_db).

The load-bearing D5 property: a provider the tenant has not opted into is **never
a routing candidate** — not merely a low-scoring one. Plus the auditable opt-in
round-trip: informed consent (current disclosure version), revocable, and the
revoke bites on the very next call because the allow-list is read live.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

import src.ai.orm  # noqa: F401 — register FK targets
from src.auth.models import Company  # noqa: F401
from src.ai.intelligence.allow_list import (
    CURRENT_DISCLOSURE_VERSION,
    DisclosureError,
    default_allowed_providers,
    effective_allow,
    opt_in,
    revoke,
)
from src.ai.intelligence.catalog import ModelSpec, PriceSpec
from src.ai.intelligence.models import ModelStatus
from src.ai.intelligence.registry import RegistryService
from src.ai.intelligence.router import IntelligenceRouter
from src.ai.intelligence.types import RoutingSignals
from src.common.security import encrypt_api_key

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

_PROV = "testprovd5"          # stands in for a China-hosted, opt-in-only provider


def _spec() -> ModelSpec:
    """Deliberately ACTIVE — so the *only* thing keeping it out of candidates is
    the D5 allow-list, not the EVX status gate."""
    return ModelSpec(
        model_key=f"{_PROV}-m", provider=_PROV, model_name="m-d5", version="1", region="cn",
        capability_profile={"reasoning_strength": 0.8, "tool_reliability": 0.8,
                            "max_context": 100000, "latency_class": "standard",
                            "modalities": ["text"], "supports_tools": True},
        data_flow={"data_region": "cn", "subprocessor": "test",
                   "trains_on_customer_data": True, "default_allowed": False},
        status=ModelStatus.ACTIVE, prices=(PriceSpec("input_token", Decimal("0.0005")),),
    )


@pytest_asyncio.fixture
async def company_with_bound_optin_model():
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
            "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"d5-{cid.hex[:8]}"})
        await RegistryService(s).install_model_catalog([_spec()])
        cat_id = (await s.execute(text(
            "SELECT id FROM model_registry WHERE provider = :p"), {"p": _PROV})).scalar()
        # The tenant HAS credentials for it and it IS bound — only consent is missing.
        await s.execute(text(
            "INSERT INTO integration_registry (id, company_id, provider_name, model_name, "
            "service_sku, service_category, component_type, encrypted_api_key, internal_cost, "
            "cost_unit, status, model_registry_id, created_at, updated_at) VALUES "
            "(:id, :c, :p, 'm-d5', :sku, 'LLM', 'input_token', :k, 0.0005, '1k tokens', "
            "'active', :cat, now(), now())"),
            {"id": str(uuid.uuid4()), "c": str(cid), "p": _PROV,
             "sku": f"{_PROV}-{cid.hex[:6]}", "k": encrypt_api_key("k"), "cat": str(cat_id)})
        await s.commit()
    try:
        yield cid
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM company_provider_optin WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM routing_decisions WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM integration_registry WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text(
                "DELETE FROM model_prices WHERE model_registry_id IN "
                "(SELECT id FROM model_registry WHERE provider = :p)"), {"p": _PROV})
            await s.execute(text("DELETE FROM model_registry WHERE provider = :p"), {"p": _PROV})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


async def test_shipped_providers_are_default_allowed_fleet_ones_are_not(company_with_bound_optin_model):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        defaults = await default_allowed_providers(db)
    assert {"anthropic", "google", "azure_openai"} <= defaults
    # The China-hosted fleet — and our stand-in — are never default-allowed.
    assert not ({"zhipu", "alibaba", "moonshot", _PROV} & defaults)


async def test_opt_in_requires_the_current_disclosure_version(company_with_bound_optin_model):
    from src.common.database import AsyncSessionLocal
    cid = company_with_bound_optin_model
    async with AsyncSessionLocal() as db:
        with pytest.raises(DisclosureError):
            await opt_in(db, cid, _PROV, disclosure_version="1999-01-01")
    # Nothing was recorded — you cannot accept terms you have not seen.
    async with AsyncSessionLocal() as db:
        assert _PROV not in await effective_allow(db, cid)


async def test_optin_then_revoke_round_trip(company_with_bound_optin_model):
    from src.common.database import AsyncSessionLocal
    cid = company_with_bound_optin_model

    async with AsyncSessionLocal() as db:
        await opt_in(db, cid, _PROV, disclosure_version=CURRENT_DISCLOSURE_VERSION)
    async with AsyncSessionLocal() as db:
        assert _PROV in await effective_allow(db, cid)

    async with AsyncSessionLocal() as db:
        assert await revoke(db, cid, _PROV) is True
    async with AsyncSessionLocal() as db:
        assert _PROV not in await effective_allow(db, cid)   # bites immediately


async def test_a_provider_without_consent_is_never_a_routing_candidate(company_with_bound_optin_model):
    """The D5 property: credentialed + bound + catalog-ACTIVE is still not enough —
    without consent the router never even scores it."""
    from src.common.database import AsyncSessionLocal
    cid = company_with_bound_optin_model

    async with AsyncSessionLocal() as db:
        r = IntelligenceRouter(db, cid)
        signals = await r._enrich(RoutingSignals(task_type="text_generation"))
        assert _PROV not in (signals.allow_list or ())
        assert not [c for c in await r._candidates(signals) if c.provider == _PROV]

    # Consent granted → the same model becomes a candidate.
    async with AsyncSessionLocal() as db:
        await opt_in(db, cid, _PROV, disclosure_version=CURRENT_DISCLOSURE_VERSION)
    async with AsyncSessionLocal() as db:
        r = IntelligenceRouter(db, cid)
        signals = await r._enrich(RoutingSignals(task_type="text_generation"))
        assert _PROV in (signals.allow_list or ())
        assert [c for c in await r._candidates(signals) if c.provider == _PROV]
