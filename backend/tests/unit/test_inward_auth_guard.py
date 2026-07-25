"""VG-05 — the tier gate on the REST path.

The two pure mappings the HTTP surface depends on: what tier *responding to an
approval* is, and whether an entity edit *raises* an autonomy band. Both are
unit-testable without a database on purpose — the gate owns no policy, so
these tests are about the mapping being faithful, not about the §20 matrix.

The load-bearing property, asserted below: a console click and a Pragya
utterance describing the same act must classify to the same tier. That
equivalence is the whole reason this module exists.
"""
from __future__ import annotations

import pytest

from src.ai.inward_auth.guard import intent_for_approval, raises_autonomy
from src.ai.inward_auth.tiers import IntentKind, Tier, classify
from src.ai.schemas.governance import AutonomyLevel


# ── intent_for_approval ───────────────────────────────────────────────────────

def test_uncategorised_approval_is_routine_work_not_ambiguity():
    """A non-policy checkpoint never passed through the §20 matrix.

    It is not "an act we failed to classify" — it is an act with no external
    business effect, so it stays T1 and any bound console session clears it.
    Getting this wrong would put a step-up in front of every ordinary approval
    a Solo Pack tenant sees.
    """
    intent = intent_for_approval({"reason": "plan wants confirmation"})
    assert intent.kind == IntentKind.WORK_ASSIGNMENT
    assert classify(intent).tier is Tier.T1


@pytest.mark.parametrize("snapshot", [None, {}, "not-a-dict", {"category": None},
                                      {"category": "generic"}])
def test_missing_or_generic_category_degrades_to_routine(snapshot):
    """Every shape a legacy row can take still classifies, and none fails up."""
    assert classify(intent_for_approval(snapshot)).tier is Tier.T1


def test_categorised_approval_inherits_the_matrix_tier():
    intent = intent_for_approval({"category": "email_dispatch"})
    assert intent.kind == IntentKind.CATEGORISED_ACTION
    assert classify(intent).tier is Tier.T2


def test_high_impact_within_band_is_sensitive_not_irreversible():
    """A payout inside its band is T2 — a ceremony, not a second channel."""
    intent = intent_for_approval({"category": "payout", "amount": 100.0, "band": 500.0})
    assert classify(intent).tier is Tier.T2


def test_high_impact_above_band_demands_the_second_channel():
    intent = intent_for_approval({"category": "payout", "amount": 900.0, "band": 500.0})
    assert classify(intent).tier is Tier.T3


def test_high_impact_without_an_amount_fails_up():
    """The regression the PolicyGate's new ``amount`` field exists to prevent.

    Before the snapshot carried the amount, *every* payout approval landed
    here — T3 by artifact rather than by policy. This test pins the failing-up
    behaviour as correct for a genuinely unknown amount, so the fix is the
    gate supplying the number, never the guard relaxing the rule.
    """
    intent = intent_for_approval({"category": "payout", "band": 500.0})
    assert classify(intent).tier is Tier.T3


@pytest.mark.parametrize("raw,expected", [
    ("250", 250.0), (250, 250.0), (250.5, 250.5),
    (None, None), ("", None), ("abc", None), (True, None),
])
def test_amount_coercion_is_total_over_json_shapes(raw, expected):
    """The snapshot is JSON, so the amount arrives as whatever was written."""
    assert intent_for_approval({"category": "payout", "amount": raw}).amount == expected


def test_a_click_and_an_utterance_classify_identically():
    """The equivalence this module exists to restore.

    Pragya's path builds the intent from an utterance; the console builds it
    from the approval's snapshot. Same act, same tier — otherwise the cheapest
    way to skip a ceremony is to stop talking and start clicking.
    """
    from src.ai.inward_auth.tiers import CommandIntent

    spoken = CommandIntent(kind=IntentKind.CATEGORISED_ACTION, category="refund",
                           amount=100.0, band=200.0)
    clicked = intent_for_approval({"category": "refund", "amount": 100.0, "band": 200.0})
    assert classify(spoken).tier is classify(clicked).tier


# ── raises_autonomy ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("before,after,expected", [
    ("A1", "A2", True),     # the act the gate exists for
    ("A0", "A3", True),
    ("A2", "A1", False),    # lowering is always safe
    ("A2", "A2", False),    # no change
    ("A3", "A0", False),
])
def test_only_an_upward_move_is_certified(before, after, expected):
    assert raises_autonomy({"autonomy_level": before}, {"autonomy_level": after}) is expected


def test_an_edit_that_touches_no_governance_is_not_a_raise():
    assert raises_autonomy({"autonomy_level": "A1"}, None) is False


def test_an_unknown_stored_level_reads_as_a_raise():
    """Ambiguity resolves toward the gate, per the AUTH convention.

    An entity whose stored band we cannot rank might be anywhere, so moving it
    to a level we *can* rank is treated as a raise and costs a ceremony.
    """
    assert raises_autonomy({"autonomy_level": "wat"}, {"autonomy_level": "A0"}) is True


def test_enum_and_dict_forms_agree():
    """The stored block is JSON; the incoming one is a pydantic Governance."""
    class _Gov:
        autonomy_level = AutonomyLevel.A2

    assert raises_autonomy({"autonomy_level": "A1"}, _Gov()) is True
    assert raises_autonomy({"autonomy_level": "A3"}, _Gov()) is False


def test_connector_binding_is_sensitive():
    """Handing an external system live credentials is T2, like enrolling a channel."""
    from src.ai.inward_auth.tiers import CommandIntent

    assert classify(CommandIntent(kind=IntentKind.CONNECTOR_BINDING)).tier is Tier.T2


# ── the refusal shape the console acts on ─────────────────────────────────────

def test_refusal_carries_the_command_it_refused():
    """A T3 refusal must name its command or the act cannot be completed.

    The out-of-band leg binds its nonce to a ``command_ref``; a refusal that
    omits one leaves the console with nothing to bind to, so the ceremony it
    just told the user to run cannot finish. The server supplies the reference
    — one the client invented would let a confirmation for one command
    authorise another.
    """
    from src.ai.inward_auth.guard import tier_refusal
    from src.ai.inward_auth.sessions import require_tier

    session = _unelevated_session()
    decision = require_tier(session, Tier.T3)
    assert decision.needs_oob is True

    exc = tier_refusal(decision, "T3", "irreversible payout",
                       command_ref="approval:abc", command_summary="a payout approval")
    assert exc.status_code == 403
    assert exc.detail["error"] == "step_up_required"
    assert exc.detail["command_ref"] == "approval:abc"
    assert exc.detail["command_summary"] == "a payout approval"
    assert exc.detail["needs_oob"] is True


def test_refusal_keys_are_present_even_when_unnamed():
    """The console reads the same keys either way — absence is null, not missing."""
    from src.ai.inward_auth.guard import tier_refusal
    from src.ai.inward_auth.sessions import require_tier

    exc = tier_refusal(require_tier(_unelevated_session(), Tier.T2), "T2", "why")
    assert exc.detail["command_ref"] is None
    assert exc.detail["command_summary"] is None


def _unelevated_session():
    """A bound console session holding nothing beyond the login."""
    from src.ai.inward_auth.models import AccountManagerSession, AuthLevel, ChannelKind

    return AccountManagerSession(
        channel_kind=ChannelKind.CONSOLE,
        auth_level=AuthLevel.BOUND,
        failed_stepups=0,
    )


# ── approval_summary ──────────────────────────────────────────────────────────

def test_summary_names_the_category_and_the_money():
    """The human confirms while reading what they are confirming."""
    from src.ai.inward_auth.guard import approval_summary

    assert approval_summary({"category": "payment_execution", "amount": 5000}) == (
        "a payment execution approval for 5,000.00")


def test_summary_of_an_uncategorised_card_claims_nothing():
    from src.ai.inward_auth.guard import approval_summary

    assert approval_summary({"reason": "confirm the plan"}) == "this approval"
    assert approval_summary(None) == "this approval"
