"""Inc 5 / REG — the registry service against a real Postgres (needs_db).

Isolated by a test-only ``provider='testprov'`` so it never collides with the
seeded real catalog and is order-independent. Proves the three load-bearing
properties: install idempotence, the effective-dated price-window invariant
(close+insert, never mutate, point-in-time resolution), and candidate filtering.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.intelligence.catalog import ModelSpec, PriceSpec
from src.ai.intelligence.models import ModelStatus
from src.ai.intelligence.registry import RegistryService

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

_PROV = "testprov"


def _cap(ctx: int, modalities: tuple[str, ...]) -> dict:
    return {"reasoning_strength": 0.8, "tool_reliability": 0.8, "max_context": ctx,
            "latency_class": "standard", "modalities": list(modalities), "supports_tools": True}


def _flow() -> dict:
    return {"data_region": "us", "subprocessor": "test", "trains_on_customer_data": False,
            "default_allowed": True}


def _spec(model_name: str, *, ctx: int = 200_000, modalities: tuple[str, ...] = ("text", "vision"),
          status: str = ModelStatus.ACTIVE, in_price: str = "0.001") -> ModelSpec:
    return ModelSpec(
        model_key=f"{_PROV}-{model_name}", provider=_PROV, model_name=model_name,
        version="1", region="us", capability_profile=_cap(ctx, modalities),
        data_flow=_flow(), status=status,
        prices=(PriceSpec("input_token", Decimal(in_price)),
                PriceSpec("output_token", Decimal("0.002"))),
    )


@pytest_asyncio.fixture
async def clean_testprov():
    import os
    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import engine
    await engine.dispose()

    async def _wipe() -> None:
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            await s.execute(text(
                "DELETE FROM model_prices WHERE model_registry_id IN "
                "(SELECT id FROM model_registry WHERE provider = :p)"), {"p": _PROV})
            await s.execute(text("DELETE FROM model_registry WHERE provider = :p"), {"p": _PROV})
            await s.commit()

    await _wipe()
    try:
        yield
    finally:
        await _wipe()


async def test_install_is_idempotent(clean_testprov):
    from src.common.database import AsyncSessionLocal
    specs = [_spec("m-a"), _spec("m-b")]
    async with AsyncSessionLocal() as db:
        first = await RegistryService(db).install_model_catalog(specs)
    assert (first.inserted, first.price_windows_opened) == (2, 4)  # 2 models × 2 components

    async with AsyncSessionLocal() as db:
        again = await RegistryService(db).install_model_catalog(specs)
    # Re-running an unchanged catalog inserts nothing and opens no price window.
    assert again.inserted == 0
    assert again.price_windows_opened == 0


async def test_price_change_closes_window_and_history_is_reproducible(clean_testprov):
    from src.common.database import AsyncSessionLocal
    svc_specs = [_spec("m-price", in_price="0.001")]

    # Initial install: opens a window at PRICE_EPOCH (2026-01-01).
    async with AsyncSessionLocal() as db:
        await RegistryService(db).install_model_catalog(svc_specs)

    # A price change at 2026-07-01 must close the old window and open a new one.
    changed = [_spec("m-price", in_price="0.002")]
    change_at = datetime(2026, 7, 1)
    async with AsyncSessionLocal() as db:
        rep = await RegistryService(db).install_model_catalog(changed, now=change_at)
    assert rep.price_windows_opened == 1  # only the changed component reopened

    async with AsyncSessionLocal() as db:
        svc = RegistryService(db)
        row_id = (await db.execute(text(
            "SELECT id FROM model_registry WHERE provider = :p AND model_name = 'm-price'"),
            {"p": _PROV},
        )).scalar()

        # Point-in-time resolution: a March event still prices at the OLD rate
        # (history preserved — the reproducibility promise), an August event at the new.
        old = await svc.resolve_price(row_id, "input_token", datetime(2026, 3, 1))
        new = await svc.resolve_price(row_id, "input_token", datetime(2026, 8, 1))
        assert old is not None and old.unit_price == Decimal("0.001")
        assert new is not None and new.unit_price == Decimal("0.002")
        # The old window was closed, not mutated.
        assert old.effective_to == change_at
        assert old.id != new.id


async def test_eligible_filters_status_modality_context_and_allowlist(clean_testprov):
    from src.common.database import AsyncSessionLocal
    specs = [
        _spec("vision-big", ctx=200_000, modalities=("text", "vision")),
        _spec("text-small", ctx=8_000, modalities=("text",)),
        _spec("preview-vision", ctx=200_000, modalities=("text", "vision"),
              status=ModelStatus.PREVIEW),
    ]
    async with AsyncSessionLocal() as db:
        await RegistryService(db).install_model_catalog(specs)

    async with AsyncSessionLocal() as db:
        svc = RegistryService(db)
        # vision + large context, scoped to our provider → only the active vision-big.
        vis = await svc.eligible(modality="vision", min_context=100_000, allow_list=[_PROV])
        names = {r.model_name for r in vis}
        assert names == {"vision-big"}  # preview excluded; text-small excluded by modality

        # text + no context floor → both active text models, never the preview one.
        txt = await svc.eligible(modality="text", min_context=0, allow_list=[_PROV])
        assert {r.model_name for r in txt} == {"vision-big", "text-small"}

        # a disallowed provider yields no candidate at all (D5 filter-before-scoring).
        assert await svc.eligible(modality="text", allow_list=["someone-else"]) == []
