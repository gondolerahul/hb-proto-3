"""Intent extraction → tier (Inc-3 PRAGYA T2).

The property under test is one-directional: extraction may raise a tier, never
lower one. Every test here is ultimately asking "can a message that should
need a step-up get through without one?"
"""
from __future__ import annotations

from src.ai.inward_auth.tiers import IntentKind, Tier
from src.ai.pragya.intents import (
    INTENT_SCHEMA,
    classify_turn,
    screen_text,
)


# --- the screen ---------------------------------------------------------------

def test_screen_catches_the_exit_demo_command() -> None:
    assert screen_text("pause invoice chasing while I'm away") == IntentKind.PROCESS_PAUSE


def test_screen_orders_most_severe_first() -> None:
    """'stop everything' is a kill switch, not a pause, even though both match."""
    assert screen_text("stop everything right now") == IntentKind.LOOP_KILL_SWITCH


def test_screen_returns_none_for_ordinary_conversation() -> None:
    assert screen_text("how did we do this week?") is None
    assert screen_text("what does your pricing look like") is None


# --- extraction failure fails up ----------------------------------------------

def test_no_extraction_at_all_fails_up_to_t3() -> None:
    """A model that returned nothing must not become a free pass."""
    result = classify_turn("do the thing we discussed", None)
    assert result.kind == IntentKind.UNKNOWN
    assert result.tier is Tier.T3


def test_malformed_extraction_fails_up_to_t3() -> None:
    result = classify_turn("do the thing", {"summary": "no kind field"})
    assert result.tier is Tier.T3


def test_failed_extraction_still_uses_the_screen_when_it_hit() -> None:
    result = classify_turn("pause the invoice chaser", None)
    assert result.kind == IntentKind.PROCESS_PAUSE
    assert result.tier is Tier.T2
    assert result.screened_up


# --- the screen can only raise ------------------------------------------------

def test_screen_overrides_a_model_that_under_called_a_command() -> None:
    """The core adversarial case: text says pause, model says it's a read."""
    result = classify_turn(
        "just pause the invoice chasing for now",
        {"kind": IntentKind.TENANT_READ, "summary": "asking about invoices"},
    )
    assert result.kind == IntentKind.PROCESS_PAUSE
    assert result.tier is Tier.T2
    assert result.screened_up


def test_screen_does_not_lower_a_model_that_called_it_higher() -> None:
    """A pause keyword must not drag a kill-switch reading down to T2."""
    result = classify_turn(
        "stop the payouts",
        {"kind": IntentKind.LOOP_KILL_SWITCH, "summary": "kill switch"},
    )
    assert result.tier is Tier.T3
    assert not result.screened_up


def test_ordinary_reads_stay_at_t1() -> None:
    result = classify_turn(
        "how did we do this week?",
        {"kind": IntentKind.REPORT, "summary": "weekly performance"},
    )
    assert result.tier is Tier.T1
    assert not result.screened_up


def test_general_question_stays_t0_when_nothing_screens() -> None:
    result = classify_turn(
        "what can you help me with?",
        {"kind": IntentKind.GENERAL_QUESTION, "summary": "capabilities"},
    )
    assert result.tier is Tier.T0


# --- categorised money commands ----------------------------------------------

def test_above_band_payout_reaches_t3() -> None:
    result = classify_turn(
        "release the payout to the vendor",
        {"kind": IntentKind.CATEGORISED_ACTION, "category": "payout",
         "amount": 9000, "summary": "release vendor payout"},
        band=500.0,
    )
    assert result.tier is Tier.T3


def test_within_band_payout_is_t2() -> None:
    result = classify_turn(
        "release the payout to the vendor",
        {"kind": IntentKind.CATEGORISED_ACTION, "category": "payout",
         "amount": 100, "summary": "release vendor payout"},
        band=500.0,
    )
    assert result.tier is Tier.T2


def test_payout_with_no_amount_fails_up() -> None:
    """The amount is what decides T2 vs T3, so its absence must fail up."""
    result = classify_turn(
        "pay the vendor",
        {"kind": IntentKind.CATEGORISED_ACTION, "category": "payout",
         "summary": "pay vendor"},
    )
    assert result.tier is Tier.T3


# --- contract -----------------------------------------------------------------

def test_every_extracted_command_carries_a_summary_and_reason() -> None:
    result = classify_turn("pause invoice chasing", None)
    assert result.summary.strip()
    assert result.classification.reason.strip()


def test_intent_schema_enumerates_exactly_the_known_kinds() -> None:
    """The model's vocabulary and the classifier's must not drift apart."""
    enum = INTENT_SCHEMA["parameters"]["properties"]["kind"]["enum"]
    known = {v for k, v in vars(IntentKind).items() if not k.startswith("_")}
    assert set(enum) == known


# --- scoping: "everything" must be said, never inferred -----------------------

def test_an_unscoped_pause_carries_no_target() -> None:
    """commands.py refuses a targetless pause rather than pausing all of it."""
    result = classify_turn("pause invoice chasing while I'm away", None)
    assert result.kind == IntentKind.PROCESS_PAUSE
    assert result.target is None


def test_an_explicit_everything_scopes_to_all() -> None:
    for phrase in ("pause everything", "pause all agents", "pause the whole lot"):
        result = classify_turn(phrase, None)
        assert result.target == "*", phrase


def test_extraction_target_survives_and_is_not_widened() -> None:
    result = classify_turn(
        "pause invoice chasing",
        {"kind": IntentKind.PROCESS_PAUSE, "target": "Order-to-Cash",
         "summary": "pause invoice chasing"})
    assert result.target == "Order-to-Cash"
