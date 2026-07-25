"""learning/preferences.py — what a person wants their surfaces to look like.

Deliberately the dullest module in the workstream. Vihara (Increment 7) is the
consumer; LEARN ships the store now for the same reason it ships KPI history
now — a *learned* preference needs observations, and observations only
accumulate if something is recording them.

Two rules that are not dull:

**A learned value is always distinguishable from a stated one.** ``learned``
is a column, not an inference, so a surface can always show *"we set this for
you because you kept collapsing it"* and let the person disagree. A preference
silently applied is indistinguishable from a bug.

**A person's explicit choice outranks anything observed.** Once a key is set
by hand, observation stops overwriting it. The alternative — a system that
keeps re-learning past your decision — is the most irritating behaviour a
preference store can have.

Design: docs/product-road-map/increment-6/01_learn.md §9.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.learning.models import UserPreference

logger = logging.getLogger(__name__)

__all__ = [
    "KEY_NAMESPACES",
    "OBSERVATIONS_BEFORE_LEARNING",
    "InvalidPreferenceKey",
    "get_preferences",
    "set_preference",
    "learn_preference",
    "observe_density",
]


class InvalidPreferenceKey(Exception):
    """A key outside the known namespaces. Refused rather than stored."""


#: Keys are namespaced so the store cannot quietly become a general-purpose
#: per-user JSON dump — which is what every preference table becomes without
#: one. A new namespace is a code change and a review.
KEY_NAMESPACES: frozenset[str] = frozenset({"density", "notify", "surface"})

#: How many consistent observations before the platform sets something on the
#: person's behalf. Matches the learning loop's own threshold: three is a
#: pattern, one is a Tuesday.
OBSERVATIONS_BEFORE_LEARNING = 3


def _validate(key: str) -> None:
    namespace = key.split(".", 1)[0]
    if namespace not in KEY_NAMESPACES:
        raise InvalidPreferenceKey(
            f"`{key}` is not in a known namespace {sorted(KEY_NAMESPACES)}")


async def get_preferences(
    db: AsyncSession, user_id: uuid.UUID, *, prefix: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Every preference for a user, or those under one prefix.

    Returns ``{key: {"value": ..., "learned": bool}}`` — the flag travels with
    the value because a caller that renders one without the other cannot honour
    the "always distinguishable" rule.
    """
    query = select(UserPreference).where(UserPreference.user_id == user_id)
    if prefix:
        query = query.where(UserPreference.key.startswith(prefix))

    return {
        row.key: {"value": row.value, "learned": row.learned}
        for row in (await db.execute(query)).scalars().all()
    }


async def set_preference(
    db: AsyncSession, *, user_id: uuid.UUID, company_id: uuid.UUID,
    key: str, value: Any,
) -> UserPreference:
    """A person setting something by hand. Always wins, always clears ``learned``.

    The caller commits.
    """
    _validate(key)
    existing = (await db.execute(
        select(UserPreference).where(
            UserPreference.user_id == user_id, UserPreference.key == key)
    )).scalar_one_or_none()

    if existing is not None:
        existing.value = value
        existing.learned = False       # it is now a stated choice, not a guess
        return existing

    row = UserPreference(user_id=user_id, company_id=company_id, key=key,
                         value=value, learned=False)
    db.add(row)
    return row


async def learn_preference(
    db: AsyncSession, *, user_id: uuid.UUID, company_id: uuid.UUID,
    key: str, value: Any,
) -> UserPreference | None:
    """Set something *on the person's behalf* — but never over their own choice.

    Returns ``None`` when a stated preference already exists for the key. That
    is the important branch: a system that keeps re-learning past a decision
    the person made is the worst version of this feature.
    """
    _validate(key)
    existing = (await db.execute(
        select(UserPreference).where(
            UserPreference.user_id == user_id, UserPreference.key == key)
    )).scalar_one_or_none()

    if existing is not None and not existing.learned:
        logger.debug("preferences: not overwriting a stated value for %s", key)
        return None

    if existing is not None:
        existing.value = value
        existing.learned = True
        return existing

    row = UserPreference(user_id=user_id, company_id=company_id, key=key,
                         value=value, learned=True)
    db.add(row)
    return row


async def observe_density(
    db: AsyncSession, *, user_id: uuid.UUID, company_id: uuid.UUID,
    surface: str, density: str,
) -> uuid.UUID | None:
    """Record that a person chose a density on a surface. The caller commits.

    An *observation*, not a setting: it goes on the bus as
    ``learning.density_observed`` and only becomes a preference once
    :func:`learn_preference` is called with enough of them behind it. Splitting
    the two is what keeps "we noticed" separate from "we changed something",
    which is the distinction a person is entitled to.
    """
    from src.ai.signals.models import SignalSource, SignalTypes
    from src.ai.signals.service import emit_signal

    return await emit_signal(
        db,
        company_id=company_id,
        source=SignalSource.HUMAN,
        type=SignalTypes.LEARNING_DENSITY_OBSERVED,
        payload={
            "user_id": str(user_id),
            "surface": surface,
            "density": density,
        },
        object_refs=[f"user:{user_id}"],
    )
