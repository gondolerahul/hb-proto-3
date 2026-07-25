"""evolution/blast_radius.py — the five limits every automated change passes (B11).

Register **B11**: *nothing forbids a self-heal triggered by one tenant's
failures from mutating a global artifact used by all tenants.* Walking the code
found the shipped self-evolution surface is mostly careful already — the tool
synthesis pipeline scopes its writes, prompt evolution and the skill library
produce candidates a human must approve. What is missing is that the safety is
a *habit of the current call sites*, and B11 is about what nothing forbids.

This is the predicate that forbids it. Pure and total, so every limit is
unit-testable and each can be mutation-tested on its own — which matters here
more than usual: a limit nobody has watched fail is a function that returns
``None``.

**Rollback is exempt from the rate and kill-switch limits, deliberately.**
Undoing an automated change is the safe direction, and the safe direction must
never be harder than the unsafe one — the same asymmetry VG-05 established for
consent revocation and autonomy lowering. A tenant who has hit the daily change
cap, or gone read-only, must still be able to get back to where they were.

Design: docs/product-road-map/increment-6/02_sega.md §4.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "ALLOWED_FIELDS",
    "NEVER_SELF_MODIFIED",
    "BlastRadiusError",
    "ChangeKind",
    "ChangeRequest",
    "Limits",
    "DEFAULT_LIMITS",
    "admit_change",
]


class BlastRadiusError(Exception):
    """A change that must not happen. Raised, never returned as a flag.

    There is no "apply it anyway, marked risky" path: an automated change that
    fails any of these limits has no correct way to proceed, and offering the
    caller a boolean would invite one to be invented.
    """


class ChangeKind(str, Enum):
    """What an automated change is trying to do."""

    CHARTER_TUNE = "charter_tune"        # prose an agent reads (LEARN proposes)
    SCHEMA_PROPOSAL = "schema_proposal"  # an additive tenant field (§8)
    ROLLBACK = "rollback"                # restore a previous version — always safe


#: What each kind may touch. Notice what is on no list at all: the blocks that
#: decide what an agent may do, to whom, with whose money.
ALLOWED_FIELDS: dict[ChangeKind, frozenset[str]] = {
    ChangeKind.CHARTER_TUNE: frozenset({"goal", "description"}),
    ChangeKind.SCHEMA_PROPOSAL: frozenset({"fields"}),
    # A rollback restores a whole prior snapshot, so it is not field-scoped —
    # it can only ever return the entity to a state that already existed and
    # was already admitted.
    ChangeKind.ROLLBACK: frozenset(),
}

#: Named rather than left to the allow-list's silence, so a reader can see
#: *which* refusals are load-bearing. LEARN refuses to **propose** these
#: (`learning/tuning.py`) and SEGA refuses to **apply** them. The duplication is
#: deliberate: a refusal that exists in one place is one refactor from gone.
NEVER_SELF_MODIFIED: dict[str, str] = {
    "governance": "autonomy bands and approval policy are never self-modified",
    "capabilities": "authority categories and SoD tags are never self-modified",
    "logic_gate": "the loop's own control flow is never self-modified",
    "identity": "the Karuna profile and system prompt are not tuning targets",
    "metadata_extensions": "gateway profiles and channel bindings live here",
}

#: Statuses in which no automated change is admitted at all (C5's ladder).
_FROZEN_STATUSES = frozenset({"read_only", "suspended"})


@dataclass(frozen=True)
class Limits:
    """Where each limit bites. Settings-backed at the caller, defaults here."""

    #: A self-heal loop that has found a way to keep proposing is contained by
    #: arithmetic rather than by judgement.
    max_changes_per_day: int = 3
    #: The largest share of an entity's runs a canarying change may serve.
    max_canary_fraction: float = 0.25


DEFAULT_LIMITS = Limits()


@dataclass(frozen=True)
class ChangeRequest:
    """Everything the predicate needs, gathered before it is asked.

    Keeping the facts on the request (rather than letting the predicate query)
    is what makes the whole of B11's answer a pure function — and what lets the
    caller decide how to count, without the limit's meaning changing.
    """

    kind: ChangeKind
    initiator_company_id: uuid.UUID
    #: The company owning the row being changed. ``None`` means a **global**
    #: artifact — the exact case B11 is about.
    target_company_id: uuid.UUID | None
    fields: tuple[str, ...] = ()
    #: Automated changes already applied for this company today.
    changes_today: int = 0
    #: The share of the entity's traffic this change would serve.
    canary_fraction: float = 0.0
    #: The company's C5 dunning ladder position.
    subscription_status: str = "current"
    metadata: dict[str, str] = field(default_factory=dict)


def admit_change(
    request: ChangeRequest, limits: Limits = DEFAULT_LIMITS,
) -> None:
    """Admit an automated change, or raise. Pure and total.

    The order is the order the limits are argued in the design, and it is
    load-bearing in one place: **scope is checked first**, so a global-artifact
    attempt is reported as a global-artifact attempt rather than as whatever
    else happened to be wrong with it.
    """
    # ── 1. Scope. The whole of B11 in one branch.
    if request.target_company_id is None:
        raise BlastRadiusError(
            "refusing an automated change to a GLOBAL artifact "
            f"({request.kind.value}): global changes go through the "
            "platform-admin pipeline, with a human on it")
    if request.target_company_id != request.initiator_company_id:
        raise BlastRadiusError(
            "refusing a cross-tenant automated change: "
            f"{request.initiator_company_id} may not modify "
            f"{request.target_company_id}")

    # ── 2. Field allow-list.
    allowed = ALLOWED_FIELDS.get(request.kind, frozenset())
    for name in request.fields:
        if name in NEVER_SELF_MODIFIED:
            raise BlastRadiusError(
                f"refusing to modify `{name}`: {NEVER_SELF_MODIFIED[name]}")
        if name not in allowed:
            raise BlastRadiusError(
                f"refusing to modify `{name}`: not on the {request.kind.value} "
                f"allow-list {sorted(allowed)}")

    # ── 3 & 5 do not apply to a rollback: the safe direction must never be
    # harder than the unsafe one (see the module docstring).
    if request.kind is ChangeKind.ROLLBACK:
        return

    # ── 3. Rate.
    if request.changes_today >= limits.max_changes_per_day:
        raise BlastRadiusError(
            f"refusing: {request.changes_today} automated changes already today, "
            f"cap is {limits.max_changes_per_day}")

    # ── 4. Cohort cap.
    if request.canary_fraction > limits.max_canary_fraction:
        raise BlastRadiusError(
            f"refusing: a canary may serve at most "
            f"{limits.max_canary_fraction:.0%} of an entity's runs, asked for "
            f"{request.canary_fraction:.0%}")

    # ── 5. Kill switch.
    if request.subscription_status in _FROZEN_STATUSES:
        raise BlastRadiusError(
            f"refusing: this tenant is {request.subscription_status}; a tenant "
            "who has stopped paying should not find their workforce rewrote "
            "itself while they were away")
