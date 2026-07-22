"""trust/idle_cost.py — the always-on idle-cost model (E1).

Finding **E1**: the Blueprint asserts a ``$2,000/month`` always-on floor without
deriving it. Five gateways, continuous sensing, and Chronos sweeps burn money at
zero business volume, and nothing said how much. The default budget envelope
(``LOOP_DEFAULT_ENVELOPE_USD``) was a placeholder waiting on this number.

**What this module derives, and what it takes as input.** The *structure* is
read off the shipped code — every component's cadence below is the cron actually
registered in ``ai/worker.py`` or the interval actually stored on
``loop_runtime`` — so the model moves when the platform moves. The *rates*
(``usd_per_*``) are unit-cost inputs from the hosting bill; they are named,
defaulted to conservative public-cloud figures, and overridable, so replacing an
estimate with a real invoice line is a one-line change rather than a re-derivation.

**The result that matters.** The idle floor splits in two, and only one half was
ever unbounded:

* **Infrastructure** (heartbeat, watchdog, sweeper, gateway polls, tenant-DB
  residency) — DB and network work, no inference. Small, linear in tenants, and
  bounded by the cron cadences.
* **Platform-initiated inference** (dreaming, meta-review, sensing) — the
  expensive half, and the one that used to be open-ended. **B13 already caps
  it**: those attributions draw from a separate envelope at
  ``LOOP_PLATFORM_ENVELOPE_USD``, so the LLM half of the idle floor has a hard
  per-tenant ceiling by construction rather than by hope.

So the derived idle cost is *infrastructure + a capped ceiling*, which is what
makes the free tier's economics arguable at all. See
``docs/product-road-map/increment-2/05a_idle_cost_model.md`` for the numbers and
the envelope validation.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.services.cost_attribution import PLATFORM_INITIATED_ATTRIBUTIONS
from src.common.config import settings

__all__ = [
    "TIER_SOLO",
    "TIER_GROWTH",
    "IdleComponent",
    "IdleCostBreakdown",
    "UnitRates",
    "components_for_tier",
    "derive_idle_cost",
    "measured_platform_spend",
]

TIER_SOLO = "solo"
TIER_GROWTH = "growth"

DAYS_PER_MONTH = Decimal("30")


@dataclass(frozen=True)
class UnitRates:
    """Hosting unit costs — the model's inputs, not its derivations.

    Defaults are conservative public-cloud figures for a small managed
    deployment. Override from a real invoice to sharpen the model; the
    structure above does not change.
    """

    # A control-plane DB round-trip's marginal cost (CPU + IOPS share on a
    # managed Postgres). Cron sweeps are a handful of indexed queries each.
    usd_per_db_query: Decimal = Decimal("0.0000004")
    # One gateway idle poll: an outbound API call + its egress.
    usd_per_gateway_poll: Decimal = Decimal("0.000002")
    # One hour of a resident hb-tenant-db container (Solo sizing, 256MB
    # shared_buffers). Zero on the `schema` backend, which has no container.
    usd_per_tenant_db_hour: Decimal = Decimal("0.006")


@dataclass(frozen=True)
class IdleComponent:
    """One always-on cost source, with the code that sets its cadence."""

    name: str
    per_day: Decimal          # invocations (or hours, for residency) per day
    usd_per_unit: Decimal
    source: str               # where the cadence is defined — keeps the model honest

    @property
    def usd_per_month(self) -> Decimal:
        return self.per_day * self.usd_per_unit * DAYS_PER_MONTH


@dataclass(frozen=True)
class IdleCostBreakdown:
    """A tier's derived idle cost: infrastructure + the capped inference ceiling."""

    tier: str
    components: tuple[IdleComponent, ...]
    platform_inference_cap_usd: Decimal

    @property
    def infrastructure_usd_per_month(self) -> Decimal:
        return sum(
            (c.usd_per_month for c in self.components), start=Decimal("0")
        )

    @property
    def ceiling_usd_per_month(self) -> Decimal:
        """The worst case: infrastructure plus platform inference at its cap."""
        return self.infrastructure_usd_per_month + self.platform_inference_cap_usd

    def as_rows(self) -> list[dict[str, str]]:
        """Table-ready breakdown (the doc and any admin view render this)."""
        return [
            {
                "component": c.name,
                "per_day": str(c.per_day),
                "usd_per_unit": str(c.usd_per_unit),
                "usd_per_month": f"{c.usd_per_month:.4f}",
                "source": c.source,
            }
            for c in self.components
        ]


def _heartbeats_per_day() -> Decimal:
    """Loop beats per day at the shipped default pacing.

    ``loop/service.py`` seeds ``heartbeat_interval_s`` at
    ``LOOP_HEARTBEAT_SCAN_SECONDS * 2``; the every-minute scan cron only wakes
    a Loop whose interval has elapsed, so the interval — not the scan — sets
    the rate.
    """
    interval_s = Decimal(settings.LOOP_HEARTBEAT_SCAN_SECONDS) * 2
    return Decimal(86400) / interval_s


def _tenant_db_hours_per_day(tier: str) -> Decimal:
    """Resident container-hours per day for one tenant DB.

    On the ``schema`` backend there is no container, so residency is free.
    On ``container``, Solo hibernates after ``TENANT_DB_SOLO_IDLE_SECONDS`` of
    inactivity — an idle Solo tenant pays only for the idle window it takes to
    fall asleep, a few times a day. Growth+ is always-on by decision.
    """
    if settings.TENANT_DB_BACKEND != "container":
        return Decimal("0")
    if tier == TIER_GROWTH:
        return Decimal("24")
    # Solo: assume ~4 sporadic touches/day, each holding the container up for
    # one idle window before hibernation pauses it.
    idle_h = Decimal(settings.TENANT_DB_SOLO_IDLE_SECONDS) / Decimal(3600)
    return Decimal("4") * idle_h


def components_for_tier(
    tier: str = TIER_SOLO, rates: Optional[UnitRates] = None,
) -> tuple[IdleComponent, ...]:
    """The always-on components one tenant contributes, at zero business volume.

    Platform-wide crons that scan all tenants (the watchdog, the signal sweeper)
    are counted at their per-tenant marginal cost — the rows this tenant adds to
    each scan — not at their full platform cost, which does not scale per tenant.
    """
    r = rates or UnitRates()
    queries_per_beat = Decimal("6")   # schedules, parked sweep, envelope, rollup, stamp

    return (
        IdleComponent(
            "loop heartbeat", _heartbeats_per_day() * queries_per_beat,
            r.usd_per_db_query, "loop/service.py heartbeat_interval_s (scan ×2)",
        ),
        IdleComponent(
            "loop watchdog", Decimal(720), r.usd_per_db_query,
            "worker.py cron(loop_watchdog) every 2 min",
        ),
        IdleComponent(
            "signal sweeper", Decimal(1440), r.usd_per_db_query,
            "worker.py cron(signal_sweeper) every minute",
        ),
        IdleComponent(
            "gateway inbound poll", Decimal(720), r.usd_per_gateway_poll,
            "worker.py cron(email_inbound_poll) every 2 min",
        ),
        IdleComponent(
            "chronos resume scan", Decimal(288), r.usd_per_db_query,
            "worker.py cron(cortex_resume_scheduled) every 5 min",
        ),
        IdleComponent(
            "kpi rollup", Decimal(24), r.usd_per_db_query,
            "worker.py cron(kpi_rollup_refresh) hourly",
        ),
        IdleComponent(
            "tenant-db residency", _tenant_db_hours_per_day(tier),
            r.usd_per_tenant_db_hour,
            "TENANT_DB_BACKEND + TENANT_DB_SOLO_IDLE_SECONDS hibernation",
        ),
    )


def derive_idle_cost(
    tier: str = TIER_SOLO, rates: Optional[UnitRates] = None,
) -> IdleCostBreakdown:
    """The per-tenant, per-month idle cost for a tier — E1's derived number."""
    return IdleCostBreakdown(
        tier=tier,
        components=components_for_tier(tier, rates),
        # B13: the platform-initiated envelope IS the inference ceiling.
        platform_inference_cap_usd=Decimal(str(settings.LOOP_PLATFORM_ENVELOPE_USD)),
    )


async def measured_platform_spend(
    db: AsyncSession, company_id: uuid.UUID, *, days: int = 30,
    attributions: Optional[Sequence[str]] = None,
) -> Decimal:
    """Actual platform-initiated spend for a tenant over a window.

    The empirical check on the model's inference half: run it against a tenant
    with no business volume and the result is that tenant's *measured* idle
    inference cost, which should sit at or under
    ``platform_inference_cap_usd``. Returns 0 when nothing was attributed.
    """
    from datetime import datetime, timedelta

    from src.ai.orm.usage import UsageLog

    since = datetime.utcnow() - timedelta(days=days)
    wanted = list(attributions or PLATFORM_INITIATED_ATTRIBUTIONS)
    total = (await db.execute(
        select(func.coalesce(func.sum(UsageLog.calculated_cost), 0)).where(
            UsageLog.company_id == company_id,
            UsageLog.attribution.in_(wanted),
            UsageLog.timestamp >= since,
        )
    )).scalar_one()
    return Decimal(str(total))
