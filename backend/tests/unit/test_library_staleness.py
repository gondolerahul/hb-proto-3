"""Inc 6 / LIB T4 — the staleness ladder, pure.

The interesting part of this module is the *ordering*, not the SQL, so the
ladder is a pure function and this file is where it is pinned. Same treatment
SEGA's taint ladder and GATE's category resolution got.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.ai.library.provenance import SOURCE_KINDS, SourceKind, StalenessState
from src.ai.library.staleness import (
    AGE_THRESHOLD_DAYS,
    AGING_WINDOW_DAYS,
    assess,
)

TODAY = date(2026, 7, 26)


def _assess(**kw):
    base = {
        "source_kind": SourceKind.UPLOAD,
        "created_at": datetime(2026, 7, 1),
        "effective_from": None,
        "superseded_by_id": None,
        "current_state": StalenessState.FRESH,
        "now": TODAY,
    }
    base.update(kw)
    return assess(**base)


class TestOrdering:
    """First rule that fires wins, and the order is the design."""

    def test_superseded_outranks_everything(self):
        # Including a contradiction: if a replacement exists, the argument
        # about whether the old one is true is settled by the replacement.
        verdict = _assess(
            superseded_by_id="a-replacement",
            current_state=StalenessState.CONTRADICTED,
            created_at=datetime(2000, 1, 1),
        )
        assert verdict.state == StalenessState.SUPERSEDED

    def test_contradiction_outranks_age(self):
        verdict = _assess(
            current_state=StalenessState.CONTRADICTED,
            created_at=datetime(2026, 7, 25),  # a day old, clearly fresh by age
        )
        assert verdict.state == StalenessState.CONTRADICTED

    def test_contradiction_is_sticky_across_sweeps(self):
        """LIB owns the state, not a detector — so time must not clear it.

        A contradiction has nowhere else to live (§6.1: the critics raise it,
        LIB stores it). If the age rules could overwrite it, every nightly
        sweep would silently resolve every contradiction nobody had got to yet.
        """
        first = _assess(current_state=StalenessState.CONTRADICTED)
        second = _assess(current_state=first.state, now=TODAY + timedelta(days=400))
        assert second.state == StalenessState.CONTRADICTED


class TestAgeRules:
    def test_recent_upload_is_fresh(self):
        verdict = _assess(created_at=datetime(2026, 7, 20))
        assert verdict.state == StalenessState.FRESH

    def test_past_the_threshold_is_stale(self):
        threshold = AGE_THRESHOLD_DAYS[SourceKind.UPLOAD]
        verdict = _assess(created_at=datetime.combine(
            TODAY - timedelta(days=threshold), datetime.min.time()))
        assert verdict.state == StalenessState.STALE

    def test_just_inside_the_window_is_aging(self):
        threshold = AGE_THRESHOLD_DAYS[SourceKind.UPLOAD]
        age = threshold - AGING_WINDOW_DAYS
        verdict = _assess(created_at=datetime.combine(
            TODAY - timedelta(days=age), datetime.min.time()))
        assert verdict.state == StalenessState.AGING

    def test_a_day_before_the_aging_window_is_still_fresh(self):
        threshold = AGE_THRESHOLD_DAYS[SourceKind.UPLOAD]
        age = threshold - AGING_WINDOW_DAYS - 1
        verdict = _assess(created_at=datetime.combine(
            TODAY - timedelta(days=age), datetime.min.time()))
        assert verdict.state == StalenessState.FRESH

    def test_conversation_derived_ages_fastest(self):
        """The thresholds are not decoration — a 100-day-old conversation
        distillate is stale while a 100-day-old upload is fresh."""
        old = datetime(2026, 4, 1)  # 116 days before TODAY
        assert _assess(source_kind=SourceKind.CONVERSATION_DERIVED,
                       created_at=old).state == StalenessState.STALE
        assert _assess(source_kind=SourceKind.UPLOAD,
                       created_at=old).state == StalenessState.FRESH


class TestEffectiveFrom:
    """The column that earns its place (LIB §4)."""

    def test_effective_from_beats_created_at(self):
        # Uploaded today, describes 2023. Staleness computed from created_at
        # would call it fresh, which is the whole reason the column exists.
        verdict = _assess(
            created_at=datetime(2026, 7, 26),
            effective_from=date(2023, 1, 1),
        )
        assert verdict.state == StalenessState.STALE
        assert "effective from" in verdict.reason

    def test_missing_effective_from_says_so_in_the_reason(self):
        verdict = _assess(created_at=datetime(2026, 7, 20), effective_from=None)
        assert "no effective_from" in verdict.reason

    def test_no_dates_at_all_is_fresh_and_says_why(self):
        """Not stale. We know nothing about its age, and a verdict invented
        from an absent column is worse than an honest 'unknown'."""
        verdict = _assess(created_at=None, effective_from=None)
        assert verdict.state == StalenessState.FRESH
        assert "age unknown" in verdict.reason


class TestReasons:
    def test_every_verdict_carries_a_reason(self):
        """A flag whose basis is invisible is a flag people learn to dismiss."""
        cases = [
            _assess(superseded_by_id="x"),
            _assess(current_state=StalenessState.CONTRADICTED),
            _assess(created_at=datetime(2000, 1, 1)),
            _assess(created_at=datetime(2026, 7, 20)),
            _assess(created_at=None, effective_from=None),
        ]
        for verdict in cases:
            assert verdict.reason.strip(), verdict
            assert len(verdict.reason) <= 255, verdict  # the column's width

    def test_a_stale_reason_names_the_threshold_that_fired(self):
        verdict = _assess(source_kind=SourceKind.CONNECTED_DRIVE,
                          created_at=datetime(2024, 1, 1))
        assert "180-day" in verdict.reason
        assert SourceKind.CONNECTED_DRIVE in verdict.reason


class TestTotality:
    def test_every_source_kind_has_a_threshold(self):
        """The totality test GATE's 64 tools taught us to write.

        A new SourceKind without a threshold falls back to the default and
        would silently age like an upload — which might be right and might be
        badly wrong. Making it fail here forces the decision.
        """
        missing = SOURCE_KINDS - set(AGE_THRESHOLD_DAYS)
        assert not missing, f"source kinds with no staleness threshold: {missing}"

    def test_an_unknown_source_kind_gets_the_most_generous_threshold(self):
        """A gap in *our* configuration must not accuse a tenant's document."""
        verdict = _assess(source_kind="something_new_in_increment_9",
                          created_at=datetime(2026, 1, 1))  # ~206 days
        assert verdict.state == StalenessState.FRESH

    def test_every_returned_state_is_a_declared_one(self):
        from src.ai.library.provenance import STALENESS_STATES

        for kw in ({"superseded_by_id": "x"},
                   {"current_state": StalenessState.CONTRADICTED},
                   {"created_at": datetime(2000, 1, 1)},
                   {"created_at": datetime(2026, 7, 20)}):
            assert _assess(**kw).state in STALENESS_STATES
