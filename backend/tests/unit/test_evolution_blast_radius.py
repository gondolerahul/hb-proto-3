"""SEGA T1 — the five limits, each observed failing on its own (B11).

B11 says *nothing forbids* a self-heal from mutating a global artifact. The
answer has to be a thing that forbids it, and a thing that forbids it is only
real if the suite has watched it refuse. So each limit gets its own test, and
each is mutation-tested separately — remove one and exactly its tests fail.

Design: docs/product-road-map/increment-6/02_sega.md §4.
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.evolution.blast_radius import (
    ALLOWED_FIELDS,
    DEFAULT_LIMITS,
    NEVER_SELF_MODIFIED,
    BlastRadiusError,
    ChangeKind,
    ChangeRequest,
    Limits,
    admit_change,
)

COMPANY = uuid.uuid4()


def _request(**kw) -> ChangeRequest:
    base = dict(
        kind=ChangeKind.CHARTER_TUNE,
        initiator_company_id=COMPANY,
        target_company_id=COMPANY,
        fields=("goal",),
        changes_today=0,
        canary_fraction=0.1,
        subscription_status="current",
    )
    return ChangeRequest(**{**base, **kw})


def test_an_ordinary_change_is_admitted():
    """The baseline. If this ever fails, the limits have stopped being limits
    and started being a wall."""
    admit_change(_request())


# ── limit 1 · scope ──────────────────────────────────────────────────────────

def test_a_global_artifact_is_refused_by_name():
    """B11's exact scenario: `company_id IS NULL` means every tenant.

    Refused with its own message rather than falling through the cross-tenant
    branch, because "this is a global row" is the case the register is about
    and it deserves to be legible in a log.
    """
    with pytest.raises(BlastRadiusError, match="GLOBAL"):
        admit_change(_request(target_company_id=None))


def test_another_tenants_row_is_refused():
    with pytest.raises(BlastRadiusError, match="cross-tenant"):
        admit_change(_request(target_company_id=uuid.uuid4()))


def test_scope_is_checked_before_anything_else():
    """A global change that is *also* over the rate cap must still report the
    global attempt — the more serious fact, and the one an operator needs."""
    with pytest.raises(BlastRadiusError, match="GLOBAL"):
        admit_change(_request(target_company_id=None, changes_today=99,
                              subscription_status="suspended"))


# ── limit 2 · field allow-list ───────────────────────────────────────────────

@pytest.mark.parametrize("blocked", sorted(NEVER_SELF_MODIFIED))
def test_governance_shaped_blocks_are_never_self_modified(blocked):
    """Autonomy, authority, control flow, the Karuna profile, gateway bindings.

    LEARN refuses to *propose* these and SEGA refuses to *apply* them. The
    duplication is deliberate: a refusal that exists in one place is one
    refactor away from gone.
    """
    with pytest.raises(BlastRadiusError, match=blocked):
        admit_change(_request(fields=(blocked,)))


def test_an_unlisted_field_fails_closed():
    """A field added to the entity model later is opted *in*, never inherited."""
    with pytest.raises(BlastRadiusError, match="allow-list"):
        admit_change(_request(fields=("some_new_block",)))


def test_one_bad_field_among_good_ones_refuses_the_whole_change():
    """There is no partial application — a change is admitted or it is not."""
    with pytest.raises(BlastRadiusError):
        admit_change(_request(fields=("goal", "governance")))


def test_a_schema_proposal_has_its_own_allow_list():
    admit_change(_request(kind=ChangeKind.SCHEMA_PROPOSAL, fields=("fields",)))
    with pytest.raises(BlastRadiusError):
        admit_change(_request(kind=ChangeKind.SCHEMA_PROPOSAL, fields=("goal",)))


def test_the_allow_lists_and_the_never_list_do_not_overlap():
    """An overlap would make the refusal order load-bearing."""
    for allowed in ALLOWED_FIELDS.values():
        assert not (allowed & set(NEVER_SELF_MODIFIED))


# ── limit 3 · rate ───────────────────────────────────────────────────────────

def test_the_daily_cap_is_honoured_exactly():
    """A self-heal loop that keeps proposing is contained by arithmetic rather
    than by judgement."""
    cap = DEFAULT_LIMITS.max_changes_per_day
    admit_change(_request(changes_today=cap - 1))
    with pytest.raises(BlastRadiusError, match="already today"):
        admit_change(_request(changes_today=cap))


def test_the_cap_is_configurable():
    admit_change(_request(changes_today=9), Limits(max_changes_per_day=10))


# ── limit 4 · cohort ─────────────────────────────────────────────────────────

def test_a_canary_may_not_serve_most_of_the_traffic():
    """A "canary" at 80% is a deployment with a reassuring name."""
    with pytest.raises(BlastRadiusError, match="canary"):
        admit_change(_request(canary_fraction=0.8))


def test_the_cohort_cap_is_honoured_exactly():
    cap = DEFAULT_LIMITS.max_canary_fraction
    admit_change(_request(canary_fraction=cap))
    with pytest.raises(BlastRadiusError):
        admit_change(_request(canary_fraction=cap + 0.01))


# ── limit 5 · kill switch ────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["read_only", "suspended"])
def test_a_frozen_tenant_admits_no_automated_change(status):
    """A tenant who has stopped paying should not discover their workforce
    rewrote itself while they were away."""
    with pytest.raises(BlastRadiusError, match=status):
        admit_change(_request(subscription_status=status))


@pytest.mark.parametrize("status", ["current", "past_due", "grace"])
def test_a_paying_or_lapsing_tenant_still_evolves(status):
    """Grace is still full function (C5) — the ladder degrades, it does not
    cliff, and evolution should not cliff either."""
    admit_change(_request(subscription_status=status))


# ── the asymmetry ────────────────────────────────────────────────────────────

def test_a_rollback_is_exempt_from_the_rate_cap():
    """Undoing is the safe direction, and the safe direction must never be
    harder than the unsafe one — the VG-05 asymmetry, applied to evolution."""
    admit_change(_request(kind=ChangeKind.ROLLBACK, fields=(),
                          changes_today=99))


def test_a_rollback_works_for_a_frozen_tenant():
    """Especially then: a read-only tenant most needs to get back to where they
    were."""
    admit_change(_request(kind=ChangeKind.ROLLBACK, fields=(),
                          subscription_status="suspended"))


def test_a_rollback_is_still_scoped():
    """Exempt from rate and kill switch, never from scope. A rollback of
    another tenant's entity is not a safe direction, it is a cross-tenant
    write."""
    with pytest.raises(BlastRadiusError, match="GLOBAL"):
        admit_change(_request(kind=ChangeKind.ROLLBACK, fields=(),
                              target_company_id=None))
    with pytest.raises(BlastRadiusError, match="cross-tenant"):
        admit_change(_request(kind=ChangeKind.ROLLBACK, fields=(),
                              target_company_id=uuid.uuid4()))
