"""evolution/entity_canary.py — an agent change earns its way to GA (VG-10).

``intelligence/canary.py`` watches a **model** rollout: its cohort is companies,
its SLO proxy is the routed fleet's fallback rate. This watches an **entity**
change: its cohort is runs of one entity inside one tenant, and its evidence is
that entity's own failures, rejections and cost. Same shape, different subject —
and kept as two modules on purpose, because folding them would make both harder
to read for the sake of sharing about twenty lines.

Three properties worth keeping when extending this:

1. **A canary is a state, not a delay.** A Solo Pack tenant may run an entity a
   handful of times a week, so a change can sit in ``canary`` for weeks while
   the evidence honestly does not exist yet. That is correct behaviour. The
   surface must render it as a state; a verdict on three runs is noise wearing
   a decision's clothes.
2. **The cohort split is stable.** Assignment hashes the triggering signal id,
   so the same signal replayed lands on the same side — otherwise a retry would
   read as a canary result.
3. **Promotion is gated by admission, not by health alone.** ``require_independent_suites``
   (EVX §22.2) runs first: *the exam predates the student*, whether the student
   is a model or an agent.

Design: docs/product-road-map/increment-6/02_sega.md §6, §7.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.evolution.models import EntityVersion, VersionStatus

logger = logging.getLogger(__name__)

__all__ = [
    "MIN_SAMPLES",
    "CanaryThresholds",
    "DEFAULT_THRESHOLDS",
    "VersionHealth",
    "CanaryVerdict",
    "in_canary_cohort",
    "assess",
    "measure_version",
    "stamp_run_version",
    "suites_for_entity",
    "promote",
    "roll_back",
]

#: Below this many runs on either side the canary keeps observing. The floor is
#: the difference between a verdict and a coin flip, and it is the same reason
#: ``intelligence/canary.py`` has one.
MIN_SAMPLES = 10


@dataclass(frozen=True)
class CanaryThresholds:
    """How much worse the candidate may be before it is rolled back.

    Relative margins, not absolute rates: an entity whose normal failure rate is
    30% is not unhealthy for being itself — the question is whether *this
    version* is worse than *its own predecessor*.
    """

    failure_rate_margin: float = 0.10     # +10 percentage points
    rejection_rate_margin: float = 0.10
    cost_multiple: float = 1.50           # candidate may cost 1.5x the incumbent


DEFAULT_THRESHOLDS = CanaryThresholds()


@dataclass(frozen=True)
class VersionHealth:
    """What one version's runs looked like. Counts and ratios, no content."""

    runs: int = 0
    failures: int = 0
    approvals_decided: int = 0
    approvals_rejected: int = 0
    total_cost_usd: float = 0.0

    @property
    def failure_rate(self) -> float:
        return (self.failures / self.runs) if self.runs else 0.0

    @property
    def rejection_rate(self) -> float:
        return ((self.approvals_rejected / self.approvals_decided)
                if self.approvals_decided else 0.0)

    @property
    def mean_cost(self) -> float:
        return (self.total_cost_usd / self.runs) if self.runs else 0.0


@dataclass(frozen=True)
class CanaryVerdict:
    healthy: bool
    decided: bool
    reasons: tuple[str, ...] = ()

    @property
    def action(self) -> str:
        if not self.decided:
            return "observe"
        return "promote" if self.healthy else "roll_back"


def in_canary_cohort(cohort_key: str, fraction: float) -> bool:
    """Is this unit of work served by the candidate version? Pure and stable.

    A hash of the key rather than a random draw, so the same triggering signal
    always lands the same side. A retried signal that flipped cohorts would
    contaminate both sides of the comparison with the same event.
    """
    if fraction <= 0.0:
        return False
    if fraction >= 1.0:
        return True
    digest = hashlib.sha256(cohort_key.encode("utf-8")).digest()
    # First four bytes as a fraction of the space — plenty for a cohort split,
    # and deterministic across processes (unlike ``hash()``, which is salted).
    bucket = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return bucket < fraction


def assess(
    candidate: VersionHealth,
    incumbent: VersionHealth,
    thresholds: CanaryThresholds = DEFAULT_THRESHOLDS,
    *,
    min_samples: int = MIN_SAMPLES,
) -> CanaryVerdict:
    """Compare a candidate version against its predecessor. Pure.

    ``decided=False`` means *keep observing* — not healthy, not unhealthy. The
    three-way answer matters: collapsing "not enough evidence" into "healthy"
    would promote every change on a quiet week, and into "unhealthy" would roll
    back every change on one.
    """
    if candidate.runs < min_samples or incumbent.runs < min_samples:
        return CanaryVerdict(
            healthy=True, decided=False,
            reasons=(f"insufficient samples (candidate {candidate.runs}, "
                     f"incumbent {incumbent.runs}, floor {min_samples}) — "
                     "still observing",))

    reasons: list[str] = []
    if candidate.failure_rate > incumbent.failure_rate + thresholds.failure_rate_margin:
        reasons.append(
            f"failure rate {candidate.failure_rate:.0%} vs "
            f"{incumbent.failure_rate:.0%} before")
    if (candidate.rejection_rate
            > incumbent.rejection_rate + thresholds.rejection_rate_margin):
        reasons.append(
            f"humans rejected {candidate.rejection_rate:.0%} of its proposals vs "
            f"{incumbent.rejection_rate:.0%} before")
    if incumbent.mean_cost > 0 and (
            candidate.mean_cost > incumbent.mean_cost * thresholds.cost_multiple):
        reasons.append(
            f"costs {candidate.mean_cost / incumbent.mean_cost:.1f}x the previous "
            "version per run")

    if reasons:
        return CanaryVerdict(healthy=False, decided=True, reasons=tuple(reasons))
    return CanaryVerdict(
        healthy=True, decided=True,
        reasons=(f"no regression over {candidate.runs} runs",))


_HEALTH_SQL = text("""
    SELECT COUNT(DISTINCT er.id)                                AS runs,
           COUNT(DISTINCT er.id) FILTER (
               WHERE er.status IN ('FAILED', 'ERROR', 'TIMEOUT')) AS failures,
           COUNT(ha.id) FILTER (
               WHERE ha.status IN ('APPROVED', 'REJECTED'))     AS decided,
           COUNT(ha.id) FILTER (WHERE ha.status = 'REJECTED')   AS rejected,
           COALESCE(SUM(DISTINCT er.total_cost_usd), 0)         AS cost
    FROM execution_runs er
    LEFT JOIN human_approvals ha ON ha.run_id = er.id
    WHERE er.entity_version_id = :version_id
""")


async def measure_version(db: AsyncSession, version_id: uuid.UUID) -> VersionHealth:
    """Read one version's health off the telemetry that already exists.

    Note what is **not** here: the critic BLOCK rate the design listed. It lives
    in ``execution_runs.context_state``, a JSON blob rewritten wholesale by the
    loop, and a health metric read from an unversioned blob is one that will
    silently change meaning. Failures, rejections and cost are real columns.
    """
    row = (await db.execute(_HEALTH_SQL, {"version_id": version_id})).one()
    return VersionHealth(
        runs=int(row.runs or 0),
        failures=int(row.failures or 0),
        approvals_decided=int(row.decided or 0),
        approvals_rejected=int(row.rejected or 0),
        total_cost_usd=float(row.cost or 0.0),
    )


async def stamp_run_version(
    db: AsyncSession, *, entity_id: uuid.UUID, cohort_key: str, fraction: float,
) -> uuid.UUID | None:
    """Which version should serve this run — the candidate, or the incumbent?

    Returns the version id to stamp on the run, or ``None`` when the entity has
    no ledger history at all (nothing to attribute to, and nothing to compare).

    Never raises: a canary is an experiment, and an experiment must not be able
    to stop the work it is observing.
    """
    try:
        canary = (await db.execute(
            select(EntityVersion)
            .where(EntityVersion.entity_id == entity_id,
                   EntityVersion.status == VersionStatus.CANARY)
            .order_by(EntityVersion.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        incumbent = (await db.execute(
            select(EntityVersion)
            .where(EntityVersion.entity_id == entity_id,
                   EntityVersion.status == VersionStatus.GA)
            .order_by(EntityVersion.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        if canary is None:
            return incumbent.id if incumbent else None
        if incumbent is None:
            # Nothing to compare against; the candidate serves everything and
            # the canary will report "insufficient samples" forever, which is
            # honest — there is no baseline.
            return canary.id
        return canary.id if in_canary_cohort(cohort_key, fraction) else incumbent.id
    except Exception as exc:  # noqa: BLE001
        logger.debug("canary: could not stamp a version for %s: %s", entity_id, exc)
        return None


def suites_for_entity(entity: Any, incumbent: VersionHealth) -> Any:
    """Which independent suites back promoting this entity (EVX §22.2, T4).

    * ``platform_curated`` — the entity descends from a Solo Pack template, so
      the **PACK behavioural goldens** (`increment-2/03b`) cover its class.
      A tenant's hand-built agent is *not* covered, and therefore cannot be
      promoted automatically. That is a real and intended consequence: a human
      may still promote it by hand, because these limits govern **automated**
      change only.
    * ``incumbent_golden`` — a predecessor accumulated enough observed runs to
      have set a standard. This is §22.2's "the exam predates the student" in
      the form an entity can supply it: the bar was set by the previous version,
      before the candidate existed.
    """
    from src.ai.intelligence.admission import SuiteSet

    tags = getattr(entity, "tags", None) or []
    curated = any(str(t) == "solo_pack" for t in tags)
    return SuiteSet(
        incumbent_golden=incumbent.runs >= MIN_SAMPLES,
        platform_curated=curated,
    )


async def promote(
    db: AsyncSession, version: EntityVersion, *, suites: Any,
) -> EntityVersion:
    """Flip a healthy canary to GA. Raises ``AdmissionError`` if the suite rule fails.

    The admission check runs **before** the status flip, in this function rather
    than beside it — the EVX precedent (`RegistryService.activate`): a gate in
    the mutation path cannot be forgotten by a new caller.
    """
    from src.ai.intelligence.admission import require_independent_suites

    require_independent_suites(suites)

    previous = (await db.execute(
        select(EntityVersion)
        .where(EntityVersion.entity_id == version.entity_id,
               EntityVersion.status == VersionStatus.GA,
               EntityVersion.id != version.id)
    )).scalars().all()
    for row in previous:
        row.status = VersionStatus.SUPERSEDED

    version.status = VersionStatus.GA
    await _emit(db, version, "governance.entity_versioned",
                {"outcome": "promoted", "version": version.version})
    return version


async def roll_back(
    db: AsyncSession, entity: Any, version: EntityVersion, *, company_id: uuid.UUID,
) -> EntityVersion | None:
    """Restore the entity to the last GA version and mark the candidate rolled back."""
    from src.ai.evolution.ledger import restore

    target = (await db.execute(
        select(EntityVersion)
        .where(EntityVersion.entity_id == version.entity_id,
               EntityVersion.status == VersionStatus.GA)
        .order_by(EntityVersion.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    version.status = VersionStatus.ROLLED_BACK
    if target is None:
        logger.warning("canary: no GA version to roll %s back to", version.entity_id)
        await _emit(db, version, "governance.entity_rolled_back",
                    {"version": version.version, "restored_to": None})
        return None

    row = await restore(db, entity, target, company_id=company_id)
    await _emit(db, version, "governance.entity_rolled_back",
                {"version": version.version, "restored_to": target.version})
    return row


async def _emit(
    db: AsyncSession, version: EntityVersion, signal_type: str, payload: dict[str, Any],
) -> None:
    """Audit on the bus. Never raises — an audit failure must not undo a rollback."""
    try:
        from src.ai.signals.models import SignalSource
        from src.ai.signals.service import emit_signal

        await emit_signal(
            db,
            company_id=version.company_id,
            source=SignalSource.TELEMETRY,
            type=signal_type,
            payload={"entity_id": str(version.entity_id),
                     "entity_version_id": str(version.id), **payload},
            object_refs=[f"entity:{version.entity_id}"],
            dedupe_key=f"{signal_type}:{version.id}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("canary: could not emit %s for %s: %s",
                       signal_type, version.id, exc)
