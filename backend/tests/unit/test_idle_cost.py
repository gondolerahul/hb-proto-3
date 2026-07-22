"""Inc 2 / TRUST — the always-on idle-cost model (E1).

What is pinned here is that the model stays *derived*: every component's rate
comes off a shipped cadence or a named unit rate, the tenant-DB half responds to
the backend and tier that actually govern it, and the inference half is bounded
by B13's platform envelope rather than left open. If someone changes a cron
cadence or the platform cap, these move — which is the point, and the signal
that 05a_idle_cost_model.md needs regenerating.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.ai.trust.idle_cost import (
    DAYS_PER_MONTH,
    TIER_GROWTH,
    TIER_SOLO,
    IdleComponent,
    UnitRates,
    components_for_tier,
    derive_idle_cost,
)
from src.common.config import settings

D = Decimal


@pytest.fixture
def schema_backend(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_DB_BACKEND", "schema")


@pytest.fixture
def container_backend(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_DB_BACKEND", "container")


class TestComponent:
    def test_monthly_is_daily_over_the_month(self):
        c = IdleComponent("x", D("100"), D("0.001"), "test")
        assert c.usd_per_month == D("100") * D("0.001") * DAYS_PER_MONTH

    def test_a_zero_rate_component_costs_nothing(self):
        assert IdleComponent("x", D("0"), D("1"), "test").usd_per_month == 0


class TestCadenceIsDerived:
    """Each component's per_day is read off the shipped cron, not asserted."""

    def test_heartbeat_follows_the_configured_interval(self, monkeypatch):
        monkeypatch.setattr(settings, "LOOP_HEARTBEAT_SCAN_SECONDS", 60)
        base = {c.name: c.per_day for c in components_for_tier(TIER_SOLO)}
        # interval = scan × 2 = 120s → 720 beats/day × 6 queries
        assert base["loop heartbeat"] == D("4320")

        monkeypatch.setattr(settings, "LOOP_HEARTBEAT_SCAN_SECONDS", 30)
        slower = {c.name: c.per_day for c in components_for_tier(TIER_SOLO)}
        assert slower["loop heartbeat"] == D("8640")  # halved interval, doubled beats

    def test_every_component_names_its_source(self):
        for c in components_for_tier(TIER_SOLO):
            assert c.source, f"{c.name} has no cadence source"


class TestTenantDbResidency:
    def test_schema_backend_has_no_container_cost(self, schema_backend):
        rows = {c.name: c.per_day for c in components_for_tier(TIER_SOLO)}
        assert rows["tenant-db residency"] == 0

    def test_growth_is_always_on(self, container_backend):
        rows = {c.name: c.per_day for c in components_for_tier(TIER_GROWTH)}
        assert rows["tenant-db residency"] == D("24")

    def test_solo_pays_only_for_its_idle_windows(self, container_backend, monkeypatch):
        """Hibernation is the whole point — Solo must cost strictly less than always-on."""
        monkeypatch.setattr(settings, "TENANT_DB_SOLO_IDLE_SECONDS", 900)
        rows = {c.name: c.per_day for c in components_for_tier(TIER_SOLO)}
        assert rows["tenant-db residency"] == D("1")  # 4 touches × 15 min
        assert rows["tenant-db residency"] < D("24")

    def test_solo_residency_tracks_the_idle_window(self, container_backend, monkeypatch):
        monkeypatch.setattr(settings, "TENANT_DB_SOLO_IDLE_SECONDS", 1800)
        rows = {c.name: c.per_day for c in components_for_tier(TIER_SOLO)}
        assert rows["tenant-db residency"] == D("2")


class TestDerivedCost:
    def test_infrastructure_floor_is_small(self, schema_backend):
        """The E1 headline: the always-on floor is cents, not the asserted $2,000."""
        breakdown = derive_idle_cost(TIER_SOLO)
        assert breakdown.infrastructure_usd_per_month < D("1.00")

    def test_growth_costs_more_than_solo(self, container_backend):
        solo = derive_idle_cost(TIER_SOLO).infrastructure_usd_per_month
        growth = derive_idle_cost(TIER_GROWTH).infrastructure_usd_per_month
        assert growth > solo

    def test_ceiling_is_infrastructure_plus_the_b13_cap(self, schema_backend, monkeypatch):
        """The inference half is bounded by B13's envelope, by construction."""
        monkeypatch.setattr(settings, "LOOP_PLATFORM_ENVELOPE_USD", "10.00")
        b = derive_idle_cost(TIER_SOLO)
        assert b.platform_inference_cap_usd == D("10.00")
        assert b.ceiling_usd_per_month == b.infrastructure_usd_per_month + D("10.00")

    def test_ceiling_moves_with_the_platform_cap(self, schema_backend, monkeypatch):
        monkeypatch.setattr(settings, "LOOP_PLATFORM_ENVELOPE_USD", "25.00")
        assert derive_idle_cost(TIER_SOLO).platform_inference_cap_usd == D("25.00")

    def test_idle_ceiling_fits_inside_the_default_envelope(self, container_backend):
        """Validates LOOP_DEFAULT_ENVELOPE_USD — E1's stated job."""
        envelope = D(str(settings.LOOP_DEFAULT_ENVELOPE_USD))
        for tier in (TIER_SOLO, TIER_GROWTH):
            assert derive_idle_cost(tier).ceiling_usd_per_month < envelope

    def test_rates_are_overridable_without_touching_structure(self, schema_backend):
        cheap = derive_idle_cost(TIER_SOLO, UnitRates(usd_per_db_query=D("0")))
        default = derive_idle_cost(TIER_SOLO)
        assert cheap.infrastructure_usd_per_month < default.infrastructure_usd_per_month
        assert len(cheap.components) == len(default.components)

    def test_rows_render_for_the_doc(self, schema_backend):
        rows = derive_idle_cost(TIER_SOLO).as_rows()
        assert rows and all(
            {"component", "per_day", "usd_per_unit", "usd_per_month", "source"} <= r.keys()
            for r in rows
        )
