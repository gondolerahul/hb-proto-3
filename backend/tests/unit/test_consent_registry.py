"""Inc 2 / TRUST — the consent registry normalisation + seam wiring (D6).

Identity normalisation is pure; the install wiring proves the registry provider
is what KAR's ``check_outbound_consent`` seam calls once installed. The DB-backed
evaluation (DNC / unsubscribe / denial) is in test_consent_registry_db.py.
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.solo_pack.consent import (
    ConsentDecision,
    check_channel_posture,
    check_outbound_consent,
    set_channel_posture_checker,
    set_consent_checker,
)
from src.ai.trust.consent_registry import install_consent_registry, normalise_identity


class TestNormalise:
    @pytest.mark.parametrize("channel,raw,expected", [
        # Phones canonicalise to digits only, so any formatting matches.
        ("whatsapp", "whatsapp:+1 (555) 111-2222", "15551112222"),
        ("whatsapp", "+15551112222", "15551112222"),
        ("voice", "+1-555", "1555"),
        ("email", "  Jo@Example.COM ", "jo@example.com"),
    ])
    def test_normalise(self, channel, raw, expected):
        assert normalise_identity(channel, raw) == expected

    def test_phone_formatting_variants_collapse(self):
        a = normalise_identity("whatsapp", "whatsapp:+1 (555) 111-2222")
        b = normalise_identity("whatsapp", "+15551112222")
        assert a == b


class TestInstall:
    pytestmark = pytest.mark.asyncio

    async def test_install_routes_seam_to_provider(self):
        class FakeProvider:
            async def check(self, company_id, channel, to_address, purpose):
                return ConsentDecision(allowed=(to_address != "blocked"), reason="fake")

            async def check_channel(self, company_id, channel, purpose):
                return ConsentDecision(allowed=(channel != "linkedin"), reason="fake")

        install_consent_registry(FakeProvider())
        try:
            allowed = await check_outbound_consent(uuid.uuid4(), "email", "ok@x.com")
            blocked = await check_outbound_consent(uuid.uuid4(), "email", "blocked")
            assert allowed.allowed is True
            assert blocked.allowed is False and blocked.reason == "fake"
        finally:
            set_consent_checker(None)  # don't leak into other tests
            set_channel_posture_checker(None)

    async def test_install_routes_the_channel_posture_seam_too(self):
        """Inc-6 GATE T3 — one install, both seams."""
        class FakeProvider:
            async def check(self, company_id, channel, to_address, purpose):
                return ConsentDecision(allowed=True, reason="fake")

            async def check_channel(self, company_id, channel, purpose):
                return ConsentDecision(allowed=(channel != "linkedin"), reason="fake")

        install_consent_registry(FakeProvider())
        try:
            off = await check_channel_posture(uuid.uuid4(), "linkedin", "marketing")
            on = await check_channel_posture(uuid.uuid4(), "tiktok", "marketing")
            assert off.allowed is False
            assert on.allowed is True
        finally:
            set_consent_checker(None)
            set_channel_posture_checker(None)

    async def test_a_provider_missing_the_channel_check_fails_at_install(self):
        """Loudly, not silently.

        A jurisdiction pack written against the pre-GATE contract implements
        only ``check``. Installing it and quietly leaving broadcast posture
        permissive would reproduce, for that deployment, exactly the ungoverned
        outbound path this workstream closed — so the contract expansion is
        enforced where it is cheap to notice.
        """
        class StaleProvider:
            async def check(self, company_id, channel, to_address, purpose):
                return ConsentDecision(allowed=True)

        with pytest.raises(AttributeError):
            install_consent_registry(StaleProvider())
        set_consent_checker(None)
        set_channel_posture_checker(None)
