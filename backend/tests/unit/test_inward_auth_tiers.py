"""Goldens for the T0–T3 impact classifier (Inc-3 AUTH T2, §11.3).

These pin the tier *table*, not the implementation: every §20 category lands on
a tier, ambiguity fails up, and no rule can lower a tier that another rule
raised. If a future change makes one of these commands cheaper to authorise,
that is a security decision and it should be made by editing this file.
"""
from __future__ import annotations

import pytest

from src.ai.governance.authority import (
    CATEGORY_RULES,
    HIGH_IMPACT_CATEGORIES,
    CategoryRule,
)
from src.ai.inward_auth import tiers as tiers_module
from src.ai.inward_auth.tiers import (
    CommandIntent,
    IntentKind,
    Tier,
    classify,
    classify_intent,
)


# --- the §11.3 examples table -------------------------------------------------

def test_general_question_is_t0() -> None:
    intent = CommandIntent(kind=IntentKind.GENERAL_QUESTION, touches_tenant_data=False)
    assert classify_intent(intent) is Tier.T0


def test_reads_and_reports_are_t1() -> None:
    for kind in (IntentKind.TENANT_READ, IntentKind.REPORT, IntentKind.WORK_ASSIGNMENT):
        assert classify_intent(CommandIntent(kind=kind)) is Tier.T1, kind


@pytest.mark.parametrize("kind", [
    IntentKind.PROCESS_PAUSE,
    IntentKind.PROCESS_RESUME,
    IntentKind.AUTONOMY_RAISE,
    IntentKind.BINDING_CHANGE,
    IntentKind.BULK_DATA_OPERATION,
])
def test_governance_and_process_mutations_are_t2(kind: str) -> None:
    """The exit-demo command ("pause invoice chasing") lives in this row."""
    assert classify_intent(CommandIntent(kind=kind)) is Tier.T2


def test_loop_kill_switch_is_t3() -> None:
    assert classify_intent(CommandIntent(kind=IntentKind.LOOP_KILL_SWITCH)) is Tier.T3


# --- the §20 reuse: every category resolves ----------------------------------

def test_every_category_rule_lands_on_t2_or_above() -> None:
    """No §20 categorised act is ever authorisable at T1 or below."""
    for category in CATEGORY_RULES:
        tier = classify_intent(CommandIntent(
            kind=IntentKind.CATEGORISED_ACTION, category=category,
            amount=1.0, band=1000.0))
        assert tier >= Tier.T2, f"{category} classified {tier.name}"


def test_regulatory_filing_is_t3_regardless_of_amount() -> None:
    assert classify_intent(CommandIntent(
        kind=IntentKind.CATEGORISED_ACTION, category="regulatory_filing")) is Tier.T3


def test_high_impact_within_band_is_t2_above_band_is_t3() -> None:
    within = CommandIntent(kind=IntentKind.CATEGORISED_ACTION, category="payout",
                           amount=100.0, band=500.0)
    above = CommandIntent(kind=IntentKind.CATEGORISED_ACTION, category="payout",
                          amount=900.0, band=500.0)
    assert classify_intent(within) is Tier.T2
    assert classify_intent(above) is Tier.T3


def test_high_impact_uses_the_category_default_band_when_none_declared() -> None:
    """An undeclared band is not an unknown band — the matrix has a default."""
    rule = CATEGORY_RULES["refund"]
    assert rule.default_band is not None
    below = classify_intent(CommandIntent(
        kind=IntentKind.CATEGORISED_ACTION, category="refund",
        amount=rule.default_band - 1))
    above = classify_intent(CommandIntent(
        kind=IntentKind.CATEGORISED_ACTION, category="refund",
        amount=rule.default_band + 1))
    assert below is Tier.T2
    assert above is Tier.T3


def test_low_impact_category_stays_t2_at_any_amount() -> None:
    """email_dispatch has no band; a big number must not invent a T3."""
    assert "email_dispatch" not in HIGH_IMPACT_CATEGORIES
    assert classify_intent(CommandIntent(
        kind=IntentKind.CATEGORISED_ACTION, category="email_dispatch",
        amount=999_999.0)) is Tier.T2


# --- fail-up: ambiguity is always resolved upward -----------------------------

def test_unknown_intent_kind_fails_up_to_t3() -> None:
    assert classify_intent(CommandIntent(kind=IntentKind.UNKNOWN)) is Tier.T3


def test_intent_kind_outside_the_table_fails_up_to_t3() -> None:
    result = classify(CommandIntent(kind="delete_the_company"))
    assert result.tier is Tier.T3
    assert "failing up" in result.reason


def test_category_outside_the_matrix_fails_up_to_t3() -> None:
    """Pragya inventing a category must not produce a cheap tier."""
    result = classify(CommandIntent(
        kind=IntentKind.CATEGORISED_ACTION, category="wire_the_reserves"))
    assert result.tier is Tier.T3
    assert "not in the §20 matrix" in result.reason


def test_high_impact_with_unknown_amount_fails_up_to_t3() -> None:
    """The amount is exactly what decides T2 vs T3, so missing it must fail up."""
    result = classify(CommandIntent(
        kind=IntentKind.CATEGORISED_ACTION, category="payout", amount=None))
    assert result.tier is Tier.T3
    assert "unknown amount" in result.reason


def test_every_high_impact_category_currently_has_a_default_band() -> None:
    """Guards the assumption the next test has to fake: if someone adds a
    bandless high-impact category, that category silently becomes T3 for every
    amount, and they should find out here rather than in production."""
    bandless = sorted(c for c in HIGH_IMPACT_CATEGORIES
                      if CATEGORY_RULES[c].default_band is None)
    assert bandless == []


def test_high_impact_with_no_band_available_fails_up_to_t3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No shipped category is bandless, so the branch is faked to stay covered."""
    bandless = CategoryRule("payout", "before_outbound_payout_above_band",
                            "payout_usd", None, 10000.0, "usd")
    monkeypatch.setitem(tiers_module.CATEGORY_RULES, "payout", bandless)

    result = classify(CommandIntent(
        kind=IntentKind.CATEGORISED_ACTION, category="payout", amount=10.0))
    assert result.tier is Tier.T3
    assert "no band" in result.reason


# --- no rule may lower a tier another rule raised -----------------------------

def test_touches_no_tenant_data_cannot_lower_a_mutating_intent() -> None:
    """A pause claiming to touch no tenant data is contradicting itself."""
    assert classify_intent(CommandIntent(
        kind=IntentKind.PROCESS_PAUSE, touches_tenant_data=False)) is Tier.T2


def test_touches_no_tenant_data_cannot_lower_a_categorised_act() -> None:
    assert classify_intent(CommandIntent(
        kind=IntentKind.GENERAL_QUESTION, category="payout",
        amount=10.0, band=500.0, touches_tenant_data=False)) is Tier.T2


def test_read_intent_carrying_a_category_is_raised_to_t2() -> None:
    """The category raises the T1 floor rather than the floor capping it."""
    assert classify_intent(CommandIntent(
        kind=IntentKind.TENANT_READ, category="discount",
        amount=1.0, band=10.0)) is Tier.T2


def test_classification_always_carries_a_reason() -> None:
    """The reason is audit evidence and the refusal copy — never empty."""
    for kind in (IntentKind.GENERAL_QUESTION, IntentKind.REPORT,
                 IntentKind.PROCESS_PAUSE, IntentKind.LOOP_KILL_SWITCH,
                 IntentKind.UNKNOWN):
        assert classify(CommandIntent(kind=kind)).reason.strip()
