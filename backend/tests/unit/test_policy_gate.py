"""Inc 1 / GOV — PolicyGate decision table (technical doc §20.3, Blueprint §9.3).

The authority matrix is data an LLM cannot argue with. These tests pin the
pure ``evaluate_policy`` function across the autonomy ladder × authority bands
× trust hook. No DB, no LLM.
"""
from __future__ import annotations

import pytest

from src.ai.governance.policy_gate import (
    ActIntent,
    BLOCK,
    PASS,
    RAISE_HITL,
    evaluate_policy,
    intent_from_move,
)
from src.ai.schemas.governance import (
    AuthorityBands,
    AutonomyLevel,
    Governance,
)


def _gov(level: AutonomyLevel, **bands) -> Governance:
    authority = AuthorityBands(**bands) if bands else None
    return Governance(autonomy_level=level, authority=authority)


class TestUncategorised:
    def test_generic_act_always_passes(self):
        for level in AutonomyLevel:
            d = evaluate_policy(ActIntent("generic"), _gov(level))
            assert d.decision == PASS
            assert d.category == "generic"

    def test_unknown_category_passes(self):
        d = evaluate_policy(ActIntent("teleport"), _gov(AutonomyLevel.A1))
        assert d.decision == PASS


class TestAutonomyLadder:
    def test_a0_blocks_any_external_effect(self):
        d = evaluate_policy(ActIntent("payout", amount_usd=10), _gov(AutonomyLevel.A0))
        assert d.decision == BLOCK
        assert "A0" in d.reason

    def test_a1_raises_hitl_for_every_external_effect(self):
        # Even a $1 payout — A1 means a human approves every external effect.
        d = evaluate_policy(ActIntent("payout", amount_usd=1), _gov(AutonomyLevel.A1))
        assert d.decision == RAISE_HITL
        assert d.checkpoint_key == "before_outbound_payout_above_band"

    def test_a1_with_bands_still_raises(self):
        d = evaluate_policy(
            ActIntent("payout", amount_usd=1),
            _gov(AutonomyLevel.A1, payout_usd=5000),
        )
        assert d.decision == RAISE_HITL

    def test_a3_passes_within_hard_ceiling(self):
        d = evaluate_policy(ActIntent("payout", amount_usd=400), _gov(AutonomyLevel.A3))
        assert d.decision == PASS

    def test_a3_still_blocked_by_hard_ceiling(self):
        d = evaluate_policy(ActIntent("payout", amount_usd=20000), _gov(AutonomyLevel.A3))
        assert d.decision == BLOCK
        assert d.hard_block == 10000.0


class TestA2Bands:
    def test_within_band_passes(self):
        d = evaluate_policy(
            ActIntent("payout", amount_usd=400),
            _gov(AutonomyLevel.A2, payout_usd=500),
        )
        assert d.decision == PASS

    def test_above_band_raises_hitl(self):
        d = evaluate_policy(
            ActIntent("payout", amount_usd=600),
            _gov(AutonomyLevel.A2, payout_usd=500),
        )
        assert d.decision == RAISE_HITL
        assert d.band == 500.0

    def test_above_hard_ceiling_blocks_even_at_a2(self):
        d = evaluate_policy(
            ActIntent("payout", amount_usd=99999),
            _gov(AutonomyLevel.A2, payout_usd=500),
        )
        assert d.decision == BLOCK

    def test_unset_band_passes_through_at_a2(self):
        # Decision 2026-07-19: unset bands pass monetary actions through
        # until Inc 2 seeds real bands. Uses the default band unless the
        # entity has NO authority block at all AND no platform default.
        d = evaluate_policy(
            ActIntent("price_change", amount_pct=50),   # price_change hard_block=None
            _gov(AutonomyLevel.A2),                      # no authority set → default 5%
        )
        # default band (5%) applies → above band → HITL
        assert d.decision == RAISE_HITL

    def test_truly_unset_band_passes(self):
        # A category with no platform default and no tuned band → pass-through.
        d = evaluate_policy(
            ActIntent("data_deletion", is_bulk=False),
            _gov(AutonomyLevel.A2),
        )
        assert d.decision == PASS

    def test_default_band_applies_when_authority_absent(self):
        # payout default band is 500 → 600 exceeds it even with no authority block
        d = evaluate_policy(ActIntent("payout", amount_usd=600), _gov(AutonomyLevel.A2))
        assert d.decision == RAISE_HITL
        assert d.band == 500.0


class TestPercentageCategories:
    def test_discount_within_band(self):
        d = evaluate_policy(
            ActIntent("discount", amount_pct=8),
            _gov(AutonomyLevel.A2, discount_pct=10),
        )
        assert d.decision == PASS

    def test_discount_above_hard_block(self):
        d = evaluate_policy(
            ActIntent("discount", amount_pct=40),
            _gov(AutonomyLevel.A2, discount_pct=10),
        )
        assert d.decision == BLOCK  # >30% hard ceiling


class TestAlwaysHITLCategories:
    @pytest.mark.parametrize("category,key", [
        ("employment_offer", "before_employment_offer"),
        ("public_statement", "before_public_statement"),
        ("regulatory_filing", "before_regulatory_filing"),
    ])
    def test_always_hitl_even_at_a3(self, category, key):
        d = evaluate_policy(ActIntent(category), _gov(AutonomyLevel.A3))
        assert d.decision == RAISE_HITL
        assert d.checkpoint_key == key


class TestDataDeletion:
    def test_single_subject_passes_at_a2(self):
        d = evaluate_policy(ActIntent("data_deletion", is_bulk=False), _gov(AutonomyLevel.A2))
        assert d.decision == PASS

    def test_bulk_raises_at_a2(self):
        d = evaluate_policy(ActIntent("data_deletion", is_bulk=True), _gov(AutonomyLevel.A2))
        assert d.decision == RAISE_HITL


class TestTrustHook:
    def test_counterparty_trust_blocks_high_impact(self):
        # §18.6 down-payment: a counterparty-trust signal cannot drive a payout,
        # even at A3 within band.
        d = evaluate_policy(
            ActIntent("payout", amount_usd=100, counterparty_trust="counterparty"),
            _gov(AutonomyLevel.A3),
        )
        assert d.decision == BLOCK
        assert "counterparty" in d.reason

    def test_counterparty_trust_allows_low_impact(self):
        d = evaluate_policy(
            ActIntent("discount", amount_pct=5, counterparty_trust="counterparty"),
            _gov(AutonomyLevel.A2, discount_pct=10),
        )
        assert d.decision == PASS  # discount not in HIGH_IMPACT_CATEGORIES

    def test_internal_trust_unaffected(self):
        d = evaluate_policy(
            ActIntent("payout", amount_usd=100, counterparty_trust="internal"),
            _gov(AutonomyLevel.A3),
        )
        assert d.decision == PASS


class TestIntentFromMove:
    def test_explicit_action_category_wins(self):
        move = type("M", (), {"plan_fragment": [{
            "target": {"action_category": "payout", "input_parameters": {"amount": 750}},
        }]})()
        intent = intent_from_move(move, entity=None, signal_trust="counterparty")
        assert intent.action_category == "payout"
        assert intent.amount_usd == 750.0
        assert intent.counterparty_trust == "counterparty"

    def test_tool_id_maps_to_category(self):
        move = type("M", (), {"plan_fragment": [{
            "target": {"tool_id": "stripe_payout", "input_parameters": {"amount_usd": 200}},
        }]})()
        intent = intent_from_move(move, entity=None, signal_trust=None)
        assert intent.action_category == "payout"
        assert intent.amount_usd == 200.0

    def test_uncategorised_move(self):
        move = type("M", (), {"plan_fragment": [{
            "target": {"tool_id": "web_search", "input_parameters": {"q": "hi"}},
        }]})()
        intent = intent_from_move(move, entity=None, signal_trust=None)
        assert intent.action_category == "generic"

    def test_discount_pct_extraction(self):
        move = type("M", (), {"plan_fragment": [{
            "action_category": "discount", "input_parameters": {"discount_pct": 15},
        }]})()
        intent = intent_from_move(move, entity=None, signal_trust=None)
        assert intent.action_category == "discount"
        assert intent.amount_pct == 15.0


class TestEmailDispatch:
    """Inc-2 SLICE: outbound email is a categorised effect — A1 quote-send → HITL."""

    def test_a1_email_send_raises_hitl(self):
        d = evaluate_policy(ActIntent("email_dispatch"), _gov(AutonomyLevel.A1))
        assert d.decision == RAISE_HITL
        assert d.checkpoint_key == "before_high_value_email_dispatch"

    def test_a2_email_send_autonomous(self):
        d = evaluate_policy(ActIntent("email_dispatch"), _gov(AutonomyLevel.A2))
        assert d.decision == PASS

    def test_a0_email_send_blocked(self):
        d = evaluate_policy(ActIntent("email_dispatch"), _gov(AutonomyLevel.A0))
        assert d.decision == BLOCK

    def test_send_email_tool_maps_to_email_dispatch(self):
        move = type("M", (), {"plan_fragment": [{
            "target": {"tool_id": "send_email", "input_parameters": {"to": "x@y.com"}},
        }]})()
        intent = intent_from_move(move, entity=None, signal_trust=None)
        assert intent.action_category == "email_dispatch"
