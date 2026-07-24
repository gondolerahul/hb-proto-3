"""inward_auth/guard.py — the tier gate on the **REST** path (VG-05).

Increment 3 built ``require_tier`` and wired it into Pragya, so *asking* for a
sensitive act in conversation costs a ceremony. Nothing wired it into the HTTP
surface, so *clicking* the same act cost nothing: a plain session could approve
a payout, hand a connector its OAuth credentials, or raise an agent's autonomy
band. The classifier already called all three T2 — only the console disagreed.

This module is that missing half. It is deliberately thin: it owns **no policy**
of its own, it only carries an intent to :func:`~src.ai.inward_auth.tiers.classify`
and the answer to :func:`~src.ai.inward_auth.sessions.require_tier`. If the
console and Pragya ever disagree about a tier, it is a bug in one call site's
*intent*, never in two copies of the rules.

Two properties worth keeping when extending it:

1. **The refusal is an instruction.** A 403 from here carries ``needs_step_up`` /
   ``needs_oob`` / ``locked`` so the caller opens the right ceremony instead of
   guessing — the same body ``inward_auth.api._require_t2_console`` already
   returns, so one frontend handler serves both.
2. **Nothing here elevates.** Per the AUTH convention, a verify function never
   elevates; only the ``/ai/authn/*`` routes do, because a failure has to be
   counted against the lockout counter. This module can only ever *refuse*.
"""
from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.models import AccountManagerSession, ChannelKind
from src.ai.inward_auth.sessions import get_or_create_session, require_tier
from src.ai.inward_auth.tiers import CommandIntent, IntentKind, classify
from src.auth.models import User

__all__ = [
    "enforce_kind",
    "enforce_tier",
    "intent_for_approval",
    "raises_autonomy",
    "tier_refusal",
]


def intent_for_approval(snapshot: Any) -> CommandIntent:
    """The intent of *responding to* a HITL approval, read off its snapshot.

    Pure, so the mapping is unit-testable without a database. The snapshot is
    written by the PolicyGate (never by user input), so its ``category`` /
    ``band`` / ``amount`` are trusted the same way the gate's own decision is.

    An approval with **no category** is not ambiguity — it is a non-policy
    checkpoint (a plan asking for confirmation), which by construction never
    passed through the §20 matrix and carries no external business effect. Those
    classify as routine work assignment (T1, satisfied by any bound session), so
    this gate does not disturb the ordinary approvals a Solo Pack tenant sees.
    Anything the gate *did* categorise inherits the §20 tier — the same answer
    Pragya gives for the same act, which is the whole point.
    """
    snap = snapshot if isinstance(snapshot, dict) else {}
    category = snap.get("category")
    if not category or category == "generic":
        return CommandIntent(kind=IntentKind.WORK_ASSIGNMENT)
    return CommandIntent(
        kind=IntentKind.CATEGORISED_ACTION,
        category=str(category),
        amount=_num(snap.get("amount")),
        band=_num(snap.get("band")),
    )


#: The A0–A4 ladder as ranks, so "is this a raise" is an ordering question and
#: never a string comparison. An unrecognised level ranks below A0, which makes
#: any move *to* a recognised level from an unrecognised one read as a raise —
#: the safe direction for a gate.
_AUTONOMY_RANK: dict[str, int] = {"A0": 0, "A1": 1, "A2": 2, "A3": 3, "A4": 4}


def raises_autonomy(stored: Any, incoming: Any) -> bool:
    """True when an entity edit moves the autonomy band *upward*.

    Only a raise is a certified act. Renaming an agent, retuning a band
    downward, or editing any other governance field is ordinary work — gating
    those would make the tier ceremony noise, and a gate that fires constantly
    is a gate people learn to click through.
    """
    if incoming is None:
        return False
    before = _AUTONOMY_RANK.get(_autonomy_of(stored), -1)
    after = _AUTONOMY_RANK.get(_autonomy_of(incoming), -1)
    return after > before


def _autonomy_of(gov: Any) -> str:
    """Read ``autonomy_level`` off either a Governance model or a raw dict."""
    if gov is None:
        return ""
    raw = gov.get("autonomy_level") if isinstance(gov, dict) else getattr(
        gov, "autonomy_level", None)
    if raw is None:
        return ""
    return str(getattr(raw, "value", raw))


def _num(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def tier_refusal(decision: Any, tier_name: str, why: str) -> HTTPException:
    """The one refusal shape every certified endpoint returns."""
    return HTTPException(status_code=403, detail={
        "error": "step_up_required",
        "tier": tier_name,
        "why": why,
        "reason": decision.reason,
        "current_level": decision.current_level,
        "required_level": decision.required_level,
        "needs_step_up": decision.needs_step_up,
        "needs_oob": decision.needs_oob,
        "locked": decision.locked,
    })


async def enforce_tier(
    db: AsyncSession,
    user: User,
    intent: CommandIntent,
) -> AccountManagerSession:
    """Classify ``intent`` and refuse unless this console session may run it.

    For endpoints whose tier depends on the payload — an approval's category,
    whether an edit actually *raises* a band. Endpoints whose intent is fixed
    by their path use :func:`enforce_kind`.

    Returns the session on success so the caller can record what authorised it.
    """
    session = await get_or_create_session(
        db,
        company_id=cast(uuid.UUID, user.company_id),
        user_id=cast(uuid.UUID, user.id),
        channel_kind=ChannelKind.CONSOLE,
    )
    result = classify(intent)
    decision = require_tier(session, result.tier)
    if not decision.allowed:
        # The session row may have just been created; keep it rather than
        # losing the lockout/activity state to the rollback the 403 triggers.
        await db.commit()
        raise tier_refusal(decision, result.tier.name, result.reason)
    return session


async def enforce_kind(
    db: AsyncSession,
    user: User,
    kind: str,
    category: str | None = None,
) -> AccountManagerSession:
    """:func:`enforce_tier` for a route whose intent is fixed by its path.

    The tier is still *derived* — passing an ``IntentKind`` and letting
    :func:`classify` decide is what keeps this surface honest when the §20
    matrix changes underneath it.

    This is deliberately a call in the handler body rather than a FastAPI
    ``dependencies=[Depends(...)]`` entry. The repo's router tests invoke
    handler functions directly, and a declarative dependency does not run on a
    direct call — so a decorator-shaped gate would be invisible to every test
    that claims to cover the route, and deleting it would break nothing. A
    security control the suite cannot observe failing is a control that does
    not exist.
    """
    return await enforce_tier(db, user, CommandIntent(kind=kind, category=category))
