"""inward_auth/tiers.py — the T0–T3 impact classifier (§11.3, pure).

The rule this file exists to enforce: *identity is never carried further than
its proof strength*. A command's tier is how much blast radius it has, and the
tier decides how hard the caller has to prove who they are before it runs.

**One taxonomy, two enforcement points.** The tiers are computed over the same
§20 action categories the PolicyGate already evaluates
(``governance.authority.CATEGORY_RULES``) — there is deliberately no parallel
command vocabulary for Pragya to drift against. The PolicyGate asks "may this
*agent* do this?"; the classifier asks "did this *human* prove enough to ask?".

Nothing here touches the database or the clock: a classification is a statement
about a command, not about a session. ``sessions.require_tier`` is where the
answer meets a particular conversation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from src.ai.governance.authority import CATEGORY_RULES, HIGH_IMPACT_CATEGORIES

__all__ = [
    "Tier",
    "IntentKind",
    "CommandIntent",
    "Classification",
    "classify_intent",
    "classify",
]


class Tier(IntEnum):
    """Impact tiers. ``IntEnum`` so "fail up" is literally ``max()``."""

    T0 = 0  # general questions touching no tenant data — no verification
    T1 = 1  # reads/reports, routine work assignment — bound identity
    T2 = 2  # sensitive — step-up ceremony required
    T3 = 3  # critical/irreversible — step-up *plus* out-of-band confirmation


class IntentKind:
    """What Pragya understood the owner to be asking for.

    Pragya's language model produces one of these plus (where relevant) an
    action category and amount; the mapping from prose to ``IntentKind`` is
    her job, and everything downstream of it is this deterministic table.
    """

    GENERAL_QUESTION = "general_question"      # T0
    TENANT_READ = "tenant_read"                # T1
    REPORT = "report"                          # T1
    WORK_ASSIGNMENT = "work_assignment"        # T1 — routine, non-categorised
    PROCESS_PAUSE = "process_pause"            # T2
    PROCESS_RESUME = "process_resume"          # T2
    AUTONOMY_RAISE = "autonomy_raise"          # T2
    BINDING_CHANGE = "binding_change"          # T2 — enrolling a channel
    BULK_DATA_OPERATION = "bulk_data_operation"  # T2
    CATEGORISED_ACTION = "categorised_action"  # T2+, decided by its category
    LOOP_KILL_SWITCH = "loop_kill_switch"      # T3
    UNKNOWN = "unknown"                        # T3 — ambiguity fails up


#: Floors that come from the intent kind alone, before any category is read.
#: A kind may only ever be raised from its floor, never lowered.
INTENT_TIER_FLOOR: dict[str, Tier] = {
    IntentKind.GENERAL_QUESTION: Tier.T0,
    IntentKind.TENANT_READ: Tier.T1,
    IntentKind.REPORT: Tier.T1,
    IntentKind.WORK_ASSIGNMENT: Tier.T1,
    IntentKind.PROCESS_PAUSE: Tier.T2,
    IntentKind.PROCESS_RESUME: Tier.T2,
    IntentKind.AUTONOMY_RAISE: Tier.T2,
    IntentKind.BINDING_CHANGE: Tier.T2,
    IntentKind.BULK_DATA_OPERATION: Tier.T2,
    IntentKind.CATEGORISED_ACTION: Tier.T2,
    IntentKind.LOOP_KILL_SWITCH: Tier.T3,
    IntentKind.UNKNOWN: Tier.T3,
}

#: Categories with no autonomous path at any band (§9.3 "—" cells) that are
#: also irreversible in the outside world once done.
_ALWAYS_T3_CATEGORIES: frozenset[str] = frozenset({"regulatory_filing"})


@dataclass(frozen=True)
class CommandIntent:
    """A command as Pragya understood it, before it is authorised.

    ``amount`` is the money/percentage the command would move, in the unit its
    category declares. ``band`` is the acting entity's autonomous-up-to value
    when the caller knows it; left ``None``, the category's platform default
    stands in.
    """

    kind: str
    category: str | None = None
    amount: float | None = None
    band: float | None = None
    touches_tenant_data: bool = True


@dataclass(frozen=True)
class Classification:
    """The tier plus why — the reason is audit evidence and refusal copy."""

    tier: Tier
    reason: str


def _band_for(category: str, declared: float | None) -> float | None:
    if declared is not None:
        return declared
    return CATEGORY_RULES[category].default_band


def classify(intent: CommandIntent) -> Classification:
    """Classify a command intent into its impact tier, with the reason.

    The tier is the **maximum** of every floor that applies, so a rule can only
    ever raise it. That is what makes "unresolvable/ambiguous → the highest
    tier it could be" fall out of the structure instead of needing a special
    case at the end.
    """
    # An unrecognised kind is ambiguity, and ambiguity fails up.
    if intent.kind not in INTENT_TIER_FLOOR:
        return Classification(
            Tier.T3, f"unrecognised intent kind {intent.kind!r} — failing up to T3")

    tier = INTENT_TIER_FLOOR[intent.kind]
    reason = f"intent kind {intent.kind!r} floors at {tier.name}"

    # "Touches no tenant data → T0" is already carried by GENERAL_QUESTION's
    # floor, so the flag never *lowers* a tier — a kind that mutates state
    # while claiming to touch no tenant data is contradicting itself, and the
    # floor wins. The flag only short-circuits the category rules below, which
    # cannot apply to a command with no category.
    if not intent.touches_tenant_data and intent.category is None:
        return Classification(tier, f"touches no tenant data; {reason}")

    category = intent.category
    if category is None:
        return Classification(tier, reason)

    if category not in CATEGORY_RULES:
        # A category Pragya invented, or one the matrix has not learned yet.
        # Either way it is unresolvable against §20 — fail up.
        return Classification(
            Tier.T3, f"category {category!r} is not in the §20 matrix — failing up to T3")

    # Any categorised act is sensitive at minimum.
    tier = max(tier, Tier.T2)
    reason = f"category {category!r} is a §20 categorised act (T2 floor)"

    if category in _ALWAYS_T3_CATEGORIES:
        return Classification(Tier.T3, f"category {category!r} is irreversible/regulatory")

    if category in HIGH_IMPACT_CATEGORIES:
        band = _band_for(category, intent.band)
        if band is None:
            # High-impact with no band to compare against: could be above it.
            return Classification(
                Tier.T3,
                f"high-impact category {category!r} with no band to compare — failing up")
        if intent.amount is None:
            # The amount is exactly what decides T2 vs T3, and it is missing.
            return Classification(
                Tier.T3,
                f"high-impact category {category!r} with unknown amount — failing up")
        if intent.amount > band:
            return Classification(
                Tier.T3,
                f"{category!r} amount {intent.amount} above band {band} — irreversible tier")
        reason = f"{category!r} amount {intent.amount} within band {band}"

    return Classification(tier, reason)


def classify_intent(intent: CommandIntent) -> Tier:
    """The tier alone (the §11.3 signature); ``classify`` also gives the reason."""
    return classify(intent).tier
