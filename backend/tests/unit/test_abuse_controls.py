"""Inc 2 / TRUST — free-credit abuse controls (E2), the pure half.

The DB-backed throttle count and the eligibility query live in
test_abuse_controls_db.py; what is pinned here is the proxy-header handling
(the throttle keys off it) and the metadata stamp the throttle later reads.
"""
from __future__ import annotations

import pytest

from src.ai.trust.abuse_controls import (
    SIGNUP_IP_KEY,
    CreditEligibility,
    client_ip,
    is_self_service_signup,
    stamp_signup_ip,
)


class TestClientIP:
    def test_socket_peer_when_no_proxy(self):
        assert client_ip({}, "203.0.113.7") == "203.0.113.7"

    def test_forwarded_for_wins_over_peer(self):
        headers = {"x-forwarded-for": "198.51.100.5"}
        assert client_ip(headers, "10.0.0.1") == "198.51.100.5"

    def test_takes_the_first_hop_not_the_proxies(self):
        """The client the edge proxy saw is first; later hops are proxies."""
        headers = {"x-forwarded-for": "198.51.100.5, 10.0.0.1, 10.0.0.2"}
        assert client_ip(headers, "10.0.0.2") == "198.51.100.5"

    def test_header_case_insensitive(self):
        assert client_ip({"X-Forwarded-For": "198.51.100.9"}, None) == "198.51.100.9"

    def test_empty_forwarded_falls_back(self):
        assert client_ip({"x-forwarded-for": "  "}, "10.0.0.1") == "10.0.0.1"

    def test_none_when_nothing_known(self):
        assert client_ip({}, None) is None


class TestStampSignupIP:
    def test_records_ip_alongside_existing_metadata(self):
        stamped = stamp_signup_ip({"completed_steps": []}, "203.0.113.7")
        assert stamped[SIGNUP_IP_KEY] == "203.0.113.7"
        assert stamped["completed_steps"] == []

    def test_absent_ip_leaves_metadata_alone(self):
        assert stamp_signup_ip({"created_via": "x"}, None) == {"created_via": "x"}

    def test_does_not_mutate_the_input(self):
        original = {"completed_steps": []}
        stamp_signup_ip(original, "203.0.113.7")
        assert SIGNUP_IP_KEY not in original

    def test_handles_null_metadata(self):
        assert stamp_signup_ip(None, "203.0.113.7") == {SIGNUP_IP_KEY: "203.0.113.7"}


class TestSelfServiceScoping:
    """The verification gate applies to signup only — the one path an attacker
    drives. Gating on the broader "has no verified user" starves admin-created,
    OAuth, and seeded tenants of credits for no security gain (it broke the
    parity harness, whose fixture companies have no users at all)."""

    def test_password_signup_is_gated(self):
        assert is_self_service_signup({"created_via": "self_registration"})

    def test_admin_created_is_not_gated(self):
        """A human vouched for them."""
        assert not is_self_service_signup({"created_via": "admin"})

    def test_oauth_is_not_gated(self):
        """The provider verified the email — is_verified=True at creation."""
        assert not is_self_service_signup({"created_via": "oauth"})

    def test_seeded_or_fixture_company_is_not_gated(self):
        """No metadata means no signup happened at all."""
        assert not is_self_service_signup(None)
        assert not is_self_service_signup({})
        assert not is_self_service_signup({"completed_steps": []})


class TestCreditEligibility:
    def test_truthiness_tracks_the_flag(self):
        assert bool(CreditEligibility(True))
        assert not bool(CreditEligibility(False, "unverified"))

    def test_reason_is_carried_for_logging(self):
        assert CreditEligibility(False, "no verified user").reason == "no verified user"
