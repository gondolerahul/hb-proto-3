"""Inc 2 / KAR — the Karuna threat posture + the outbound consent seam.

The gateways are the attack surface. This locks the two governance guarantees
that make a hostile inbound message harmless, plus the consent hook contract:

* **Trust down-payment (§18.6):** a ``counterparty``-trust signal can never drive
  a high-impact category (payout/refund/contract/vendor) — blocked before
  autonomy is even considered. So an injection that talked a gateway into a
  payout is refused at the gate, on top of gateways carrying no money tools.
* **Consent seam:** outbound sends pass through a tenant-configured hook; TRUST
  installs the real registry, the default posture allows transactional sends.
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.governance.policy_gate import ActIntent, BLOCK, RAISE_HITL, evaluate_policy
from src.ai.schemas.governance import AutonomyLevel, Governance
from src.ai.solo_pack.consent import (
    ConsentDecision,
    check_outbound_consent,
    set_consent_checker,
)


class TestTrustDownPayment:
    """A counterparty-trust signal cannot drive money movement (injection golden)."""

    @pytest.mark.parametrize("category", ["payout", "refund", "contract", "vendor_creation"])
    def test_counterparty_trust_blocks_high_impact(self, category):
        intent = ActIntent(action_category=category, amount_usd=5000.0,
                           counterparty_trust="counterparty")
        gov = Governance(autonomy_level=AutonomyLevel.A1)  # even a proposing entity
        decision = evaluate_policy(intent, gov)
        assert decision.decision == BLOCK
        assert "counterparty-trust" in decision.reason

    def test_internal_trust_still_gated_not_blocked(self):
        # The same act from an internal (non-counterparty) signal is gated (HITL
        # at A1), not blocked — the block is specifically the counterparty taint.
        intent = ActIntent(action_category="payout", amount_usd=100.0,
                           counterparty_trust="internal")
        gov = Governance(autonomy_level=AutonomyLevel.A1)
        decision = evaluate_policy(intent, gov)
        assert decision.decision == RAISE_HITL


class TestConsentSeam:
    pytestmark = pytest.mark.asyncio

    async def test_default_allows_when_no_registry(self):
        set_consent_checker(None)  # ensure clean default
        decision = await check_outbound_consent(
            uuid.uuid4(), "whatsapp", "+15551234567", "transactional")
        assert decision.allowed is True

    async def test_installed_checker_can_deny(self):
        dnc = {"+15550000000"}

        async def checker(company_id, channel, to_address, purpose):
            if to_address in dnc:
                return ConsentDecision(allowed=False, reason="on the do-not-contact list")
            return ConsentDecision(allowed=True)

        set_consent_checker(checker)
        try:
            blocked = await check_outbound_consent(uuid.uuid4(), "whatsapp", "+15550000000")
            allowed = await check_outbound_consent(uuid.uuid4(), "whatsapp", "+15559999999")
            assert blocked.allowed is False
            assert "do-not-contact" in blocked.reason
            assert allowed.allowed is True
        finally:
            set_consent_checker(None)  # don't leak into other tests

    async def test_clearing_checker_restores_default(self):
        async def deny_all(company_id, channel, to_address, purpose):
            return ConsentDecision(allowed=False, reason="deny")

        set_consent_checker(deny_all)
        set_consent_checker(None)
        decision = await check_outbound_consent(uuid.uuid4(), "email", "a@b.com")
        assert decision.allowed is True
