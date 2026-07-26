"""Inc 6 / STRAT T4 + T5 + T7 — the pipeline rules, pure.

The interesting part of this workstream is *what a legal move is*, so those
rules are pure functions and this file is where they are pinned. Three carry
weight beyond tidiness: a Proposition adopts only from `tabled`, a Mandate
issues only from an `active` Resolution, and an honesty grade must have a run
behind it.
"""
from __future__ import annotations

import pytest

from src.ai.strategy.governance import (
    AGENT_FORBIDDEN_WRITES,
    agent_may_write,
    strategy_write_policy,
)
from src.ai.strategy.pipeline import (
    PLANNING_OBJECTS,
    check_honesty_grade,
    check_transition,
    may_adopt,
    may_issue_mandate,
    validate_write,
)
from src.ai.strategy.realized import Verdict, decide_verdict


class TestTotality:
    def test_the_governed_object_set_matches_the_spine(self):
        """A Planning object added later without a transition table would ship
        ungoverned. GATE's 64 uncategorised social tools are what this test is
        for."""
        from src.ai.tenant_schema.hbs_seed import HBS_SPINE

        planning = {o["name"] for o in HBS_SPINE
                    if o.get("module") == "Planning" and o.get("domain") == "strategy"}
        assert planning == PLANNING_OBJECTS, (
            f"spine-only: {planning - PLANNING_OBJECTS}, "
            f"table-only: {PLANNING_OBJECTS - planning}")

    def test_every_planning_object_carries_the_strategy_domain(self):
        from src.ai.tenant_schema.hbs_seed import HBS_SPINE

        for obj in HBS_SPINE:
            if obj["name"] in PLANNING_OBJECTS:
                assert obj["domain"] == "strategy", obj["name"]

    def test_budget_keeps_its_financial_domain(self):
        """Planning's pre-existing object is not swept into `strategy` — a
        budget is a financial record and a collections agent may legitimately
        need it."""
        from src.ai.tenant_schema.hbs_seed import HBS_SPINE

        budget = next(o for o in HBS_SPINE if o["name"] == "Budget")
        assert budget["domain"] == "financial"


class TestPropositionTransitions:
    def test_adoption_requires_tabling_first(self):
        """Adopting straight from draft skips the step where a human read it,
        which is the only step that makes a Resolution mean anything."""
        assert not check_transition("Proposition", "draft", "adopted")
        assert check_transition("Proposition", "tabled", "adopted")

    def test_may_adopt_agrees_with_the_table(self):
        assert may_adopt({"status": "tabled"})
        assert not may_adopt({"status": "draft"})
        assert not may_adopt({"status": "rejected"})

    def test_adopting_twice_says_so(self):
        verdict = may_adopt({"status": "adopted"})
        assert not verdict
        assert "already been adopted" in verdict.reason

    def test_adopted_is_terminal(self):
        verdict = check_transition("Proposition", "adopted", "withdrawn")
        assert not verdict
        assert "terminal" in verdict.reason

    def test_a_rejected_proposition_can_be_reconsidered(self):
        assert check_transition("Proposition", "rejected", "tabled")

    def test_an_unknown_status_is_refused_on_create(self):
        assert not check_transition("Proposition", None, "approved")
        assert check_transition("Proposition", None, "draft")


class TestResolutionAndMandate:
    def test_a_mandate_issues_only_from_an_active_resolution(self):
        assert may_issue_mandate({"status": "active"})
        assert not may_issue_mandate({"status": "revoked"})
        assert not may_issue_mandate({"status": "superseded"})

    def test_the_revoked_refusal_is_the_one_that_matters(self):
        """A revoked decision still handing out work fails *quietly* — the
        mandate it produces looks exactly like a legitimate one."""
        verdict = may_issue_mandate({"status": "revoked"})
        assert "revoked" in verdict.reason

    def test_revoked_is_terminal(self):
        """A revoked decision that can be quietly reactivated is a decision
        with no audit trail; the honest move is a new Resolution."""
        assert not check_transition("Resolution", "revoked", "active")

    def test_a_mandate_can_always_be_closed(self):
        for status in ("issued", "in_flight", "reviewed"):
            assert check_transition("Mandate", status, "closed"), status


class TestObjectivesAndTargets:
    def test_an_objective_can_be_abandoned_from_either_live_state(self):
        assert check_transition("Objective", "draft", "abandoned")
        assert check_transition("Objective", "active", "abandoned")

    def test_an_abandoned_objective_can_be_revived(self):
        assert check_transition("Objective", "abandoned", "active")

    def test_achieved_is_terminal(self):
        assert not check_transition("Objective", "achieved", "active")

    def test_a_met_target_stays_met(self):
        assert not check_transition("Target", "met", "open")


class TestObjectsWithoutLifecycles:
    def test_minutes_forecast_and_review_are_unconstrained(self):
        """A caller should not need to know which objects have lifecycles."""
        for name in ("Minutes", "Forecast", "Review"):
            assert check_transition(name, "anything", "whatever"), name

    def test_a_non_planning_object_is_untouched(self):
        assert check_transition("Invoice", "draft", "paid")
        assert validate_write("Invoice", {"status": "nonsense"})


class TestHonestyGrade:
    def test_untested_needs_no_run(self):
        assert check_honesty_grade("untested", None)
        assert check_honesty_grade(None, None)

    def test_a_real_grade_without_a_run_is_refused(self):
        """A human typing `replay` into a proposition that never went near the
        Glasshouse would launder an untested bet into the strongest grade the
        system has."""
        for grade in ("replay", "forecast", "unknown"):
            verdict = check_honesty_grade(grade, None)
            assert not verdict, grade
            assert "twin_run_id" in verdict.reason

    def test_a_real_grade_with_a_run_is_allowed(self):
        assert check_honesty_grade("replay", "1f0c…")

    def test_an_invented_grade_is_refused_even_with_a_run(self):
        assert not check_honesty_grade("excellent", "1f0c…")

    def test_the_vocabulary_matches_twins(self):
        """Planning has TWIN's three plus `untested`. The fourth is
        load-bearing: `untested` means never taken to the Glasshouse while
        `unknown` means a run happened and could not be graded, and rendering
        them identically is the softening TWIN's grading exists to prevent."""
        from src.ai.twin.grading import Grade

        twin_grades = {Grade.REPLAY, Grade.FORECAST, Grade.UNKNOWN}
        for grade in twin_grades:
            assert check_honesty_grade(grade, "run-id"), grade
        assert check_honesty_grade("untested", None)
        assert "untested" not in twin_grades

    def test_validate_write_falls_back_to_the_stored_run_id(self):
        """A write touching only the grade could otherwise never satisfy the
        rule, because the unchanged run id is absent from the delta."""
        assert validate_write(
            "Proposition", {"honesty_grade": "replay"},
            current={"twin_run_id": "abc"})
        assert not validate_write(
            "Proposition", {"honesty_grade": "replay"}, current={})


class TestAgentsMayNotAdopt:
    def test_an_agent_cannot_activate_a_resolution(self):
        refusal = agent_may_write("Resolution", {"status": "active"}, "P08")
        assert refusal is not None
        assert "only a human adopts" in refusal

    def test_a_human_write_is_not_refused_here(self):
        """The human path is gated by STRATEGY_RESOLUTION at the router — this
        predicate is about agents only."""
        assert agent_may_write("Resolution", {"status": "active"}, None) is None

    def test_an_agent_may_draft_a_proposition(self):
        assert agent_may_write(
            "Proposition", {"status": "draft", "title": "try discounting"}, "P08") is None

    def test_an_agent_may_revoke(self):
        """The safe direction must never be harder than the unsafe one."""
        assert agent_may_write("Resolution", {"status": "revoked"}, "P08") is None

    def test_the_forbidden_table_only_names_planning_objects(self):
        assert set(AGENT_FORBIDDEN_WRITES) <= PLANNING_OBJECTS

    def test_the_policy_composes_both_halves(self):
        # Ownership rule bites first...
        assert strategy_write_policy(
            "Resolution", {"status": "active"}, None, "P08") is not None
        # ...and the transition rule bites for a human.
        assert strategy_write_policy(
            "Proposition", {"status": "adopted"}, {"status": "draft"}, None) is not None
        # ...and a legal human write passes both.
        assert strategy_write_policy(
            "Proposition", {"status": "adopted"}, {"status": "tabled"}, None) is None


class TestVerdicts:
    def test_direction_decrease_inverts_the_comparison(self):
        """`days_sales_outstanding` improving means going *down*. A comparison
        that assumed higher-is-better would report a success as a miss."""
        assert decide_verdict(predicted=35, realized=30, direction="decrease",
                              window_closed=True) == Verdict.MET
        assert decide_verdict(predicted=35, realized=41, direction="decrease",
                              window_closed=True) == Verdict.MISSED

    def test_direction_increase_is_the_default_reading(self):
        assert decide_verdict(predicted=100, realized=120, direction="increase",
                              window_closed=True) == Verdict.MET

    def test_hold_never_reports_met(self):
        """Holding is a state you are still in, not one you reach — reporting
        `met` would claim a finish line that does not exist."""
        assert decide_verdict(predicted=50, realized=50, direction="hold",
                              window_closed=True) == Verdict.ON_TRACK
        assert decide_verdict(predicted=50, realized=60, direction="hold",
                              window_closed=True) == Verdict.OFF_TRACK

    def test_an_open_window_reports_track_not_outcome(self):
        assert decide_verdict(predicted=100, realized=120, direction="increase",
                              window_closed=False) == Verdict.ON_TRACK
        assert decide_verdict(predicted=100, realized=80, direction="increase",
                              window_closed=False) == Verdict.OFF_TRACK

    @pytest.mark.parametrize("predicted,realized", [(None, 10), (10, None), (None, None)])
    def test_a_missing_number_is_not_measurable_never_zero(self, predicted, realized):
        """A fabricated KPI prompts a decision while a missing one prompts a
        question, and a strategy review is where a fabricated number would do
        the most damage."""
        assert decide_verdict(predicted=predicted, realized=realized,
                              direction="increase",
                              window_closed=True) == Verdict.NOT_MEASURABLE
