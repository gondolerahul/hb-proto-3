"""learning/observation_prior.py — what the fleet has actually been observed doing.

The one consumer of the pooled store (design §4.4). `model_registry` declares a
model's `capability_profile`; this turns that declaration into a **prior** that
observation can correct — a model advertising `tool_reliability: 0.9` that has
been re-routed off a third of the time gets marked down.

Three limits, and each one exists to stop a different failure:

* **Bounded** (±``LEARN_OBSERVATION_WEIGHT``, default 0.2 on a 0–1 axis). A bad
  week must not be able to invert the ordering. A genuinely bad model gets
  removed by EVX admission, not by drift in a score.
* **Floored** (``LEARN_OBSERVATION_MIN_SAMPLES``). Below the floor there is no
  correction at all, which matters most right after deploy when the pooled
  store is empty and every model would otherwise look terrible.
* **Never status-changing.** ``RegistryService.activate`` remains the only path
  to `active` and still refuses on a failed admission. Learning adjusts
  *preference among admitted models*; admission stays a gate a preference
  cannot open.

The reading is cached briefly: the pooled store is written once a day by
``pooling.pool_day``, so re-querying it on every routed LLM call would be a
round trip per call for data that cannot have changed.

Design: docs/product-road-map/increment-6/01_learn.md §4.4.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import date, timedelta
from typing import Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = [
    "CACHE_TTL_SECONDS",
    "LOOKBACK_DAYS",
    "observed_reliability",
    "reset_cache",
]

#: How far back the pooled buckets are read. Long enough to accumulate samples
#: across the k-anonymity floor, short enough that a model's improvement after
#: a provider fix is visible within a fortnight.
LOOKBACK_DAYS = 14

#: The pooled store is written daily; a short cache is free correctness.
CACHE_TTL_SECONDS = 300.0

_cache: dict[str, tuple[float, dict[uuid.UUID, float]]] = {}


def reset_cache() -> None:
    """Test hook — drop the memoised reading."""
    _cache.clear()


_RELIABILITY_SQL = text("""
    SELECT model_registry_id,
           SUM(observations) AS observations,
           SUM(successes)    AS successes
    FROM platform_observations
    WHERE metric = 'route_outcome'
      AND bucket_day >= :since
      AND model_registry_id IS NOT NULL
    GROUP BY model_registry_id
""")


async def observed_reliability(
    db: AsyncSession,
    *,
    today: date | None = None,
    min_samples: int | None = None,
    use_cache: bool = True,
) -> Mapping[uuid.UUID, float]:
    """Observed success rate per catalog model, where there is enough of it.

    "Success" is *did not have to fall back* — inherited from
    ``pooling.bucket_decisions`` along with its limitation (the shipped
    telemetry cannot attribute a generate failure to a specific model).

    Models below the sample floor are simply **absent** from the mapping rather
    than present with a default. A caller that finds nothing applies no
    correction, which is the behaviour wanted on an empty store: the declared
    profile is the best information available and should be used unmodified.

    Never raises. A learning input that can break routing is not an input worth
    having, so a failed read logs and returns nothing.
    """
    from src.common.config import settings

    floor = (min_samples if min_samples is not None
             else int(getattr(settings, "LEARN_OBSERVATION_MIN_SAMPLES", 20)))
    at = today or date.today()
    key = f"{at.isoformat()}:{floor}"

    if use_cache:
        cached = _cache.get(key)
        if cached is not None and (time.monotonic() - cached[0]) < CACHE_TTL_SECONDS:
            return cached[1]

    try:
        rows = (await db.execute(
            _RELIABILITY_SQL, {"since": at - timedelta(days=LOOKBACK_DAYS)})).all()
    except Exception as exc:  # noqa: BLE001
        logger.debug("observed_reliability unavailable, using declared profiles: %s", exc)
        return {}

    reliability: dict[uuid.UUID, float] = {}
    for row in rows:
        observations = int(row.observations or 0)
        if observations < floor:
            continue
        reliability[row.model_registry_id] = max(
            0.0, min(1.0, float(row.successes or 0.0) / observations))

    if use_cache:
        _cache[key] = (time.monotonic(), reliability)
    return reliability
