"""Delegation copy and contract (Inc-4 PRAGYA-RT T4).

The pure half. Dispatch and the report-back loop need a database and live in
``tests/integration/test_pragya_db.py``; what is checkable here is the closed
set of delegable work and the honesty of what Pragya says about it.
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.pragya.delegation import (
    PROMISE_COPY,
    DelegationKind,
    report_copy,
)
from src.ai.pragya.models import DelegationStatus, PragyaDelegation


def _row(**kw) -> PragyaDelegation:
    base = dict(
        company_id=uuid.uuid4(), kind=DelegationKind.RESEARCH,
        status=DelegationStatus.DONE, promise="…",
        params={"subject": "your pricing"}, result=None, error=None)
    base.update(kw)
    return PragyaDelegation(**base)


# --- the set is closed --------------------------------------------------------

def test_every_kind_has_promise_copy() -> None:
    """A kind with no copy would dispatch work and say nothing about it."""
    kinds = {v for k, v in vars(DelegationKind).items() if not k.startswith("_")}
    assert set(PROMISE_COPY) == kinds


def test_every_promise_says_what_and_that_a_report_is_coming() -> None:
    """The invariant: an owner must know the work is underway, not done, and
    that they will hear back. 'I'll look into it' is how they end up believing
    something happened."""
    for kind, copy in PROMISE_COPY.items():
        assert "{subject}" in copy, kind
        rendered = copy.format(subject="X").lower()
        assert any(w in rendered for w in
                   ("i'll tell you", "i'll let you know", "i'll come back",
                    "come back to you")), kind


def test_promises_give_a_duration_where_one_is_actually_knowable() -> None:
    """Research, a board build, an ingest and an activation have rough shapes
    we can state. A generic colleague call does NOT — the child decides what
    the work is, so quoting a duration would be inventing one, and an invented
    estimate is a broken promise with extra steps."""
    knowable = {DelegationKind.RESEARCH, DelegationKind.CAPABILITY_BUILD,
                DelegationKind.BULK_INGEST, DelegationKind.ACTIVATION}
    for kind in knowable:
        rendered = PROMISE_COPY[kind].format(subject="X")
        assert any(w in rendered for w in ("minute", "moment")), kind

    generic = PROMISE_COPY[DelegationKind.COLLEAGUE].format(subject="X")
    assert "minute" not in generic


def test_promise_copy_never_claims_completion() -> None:
    for kind, copy in PROMISE_COPY.items():
        rendered = copy.format(subject="X").lower()
        assert "done" not in rendered, kind
        assert "finished" not in rendered, kind


def test_the_capability_promise_mentions_review() -> None:
    """A built capability is reviewed before it touches tenant data, and the
    owner should hear that rather than infer it."""
    copy = PROMISE_COPY[DelegationKind.CAPABILITY_BUILD]
    assert "reviewed" in copy


# --- closing the loop ---------------------------------------------------------

def test_a_completed_delegation_reports_its_summary() -> None:
    row = _row(result={"summary": "found 3 pricing tiers"})
    assert "found 3 pricing tiers" in report_copy(row)


def test_a_completed_delegation_without_a_summary_still_reports() -> None:
    """Silence is not an option — the owner was promised something."""
    assert report_copy(_row(result={})).strip()


def test_a_failed_delegation_is_reported_as_plainly_as_a_success() -> None:
    """Quietly dropping work that failed is how an owner finds out weeks later
    that the thing they were told was underway never happened."""
    row = _row(status=DelegationStatus.FAILED, error="the search provider is unconfigured")
    copy = report_copy(row)
    assert "didn't come off" in copy
    assert "the search provider is unconfigured" in copy
    # ...and it offers a way forward rather than just apologising.
    assert "?" in copy


def test_report_copy_uses_the_subject_the_owner_would_recognise() -> None:
    row = _row(params={"subject": "your invoicing setup"}, result={})
    assert "your invoicing setup" in report_copy(row)


def test_a_delegation_with_no_subject_still_produces_sensible_copy() -> None:
    row = _row(params={}, result={})
    assert report_copy(row).strip()


# --- status vocabulary --------------------------------------------------------

def test_reported_is_distinct_from_done() -> None:
    """Work that finished but was never reported is the failure the table is
    designed to surface; one status for both would hide it."""
    assert DelegationStatus.DONE != DelegationStatus.REPORTED
