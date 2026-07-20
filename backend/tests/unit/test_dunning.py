"""Inc 2 / TRUST — the graduated dunning ladder (C5).

The ladder is pure: days-past-due → subscription status, with configurable
grace + read-only windows. The DB transition + signal are in test_dunning_db.py.
"""
from __future__ import annotations

import pytest

from src.ai.trust.dunning import (
    SubscriptionStatus,
    agents_may_act,
    is_read_only,
    is_suspended,
    status_for_days_past_due,
)

S = SubscriptionStatus


class TestLadder:
    @pytest.mark.parametrize("days,expected", [
        (0, S.CURRENT), (-3, S.CURRENT),
        (1, S.PAST_DUE),
        (2, S.GRACE), (7, S.GRACE),
        (8, S.READ_ONLY), (14, S.READ_ONLY),
        (15, S.SUSPENDED), (99, S.SUSPENDED),
    ])
    def test_default_windows(self, days, expected):
        assert status_for_days_past_due(days) == expected

    def test_windows_are_configurable(self):
        # A 2-day grace, 1-day read-only compresses the ladder.
        assert status_for_days_past_due(3, grace_days=2, read_only_days=1) == S.READ_ONLY
        assert status_for_days_past_due(4, grace_days=2, read_only_days=1) == S.SUSPENDED

    def test_ladder_is_monotonic(self):
        order = [S.CURRENT, S.PAST_DUE, S.GRACE, S.READ_ONLY, S.SUSPENDED]
        seen = [status_for_days_past_due(d) for d in range(0, 20)]
        idxs = [order.index(s) for s in seen]
        assert idxs == sorted(idxs)  # never moves backwards as days grow


class TestPredicates:
    def test_agents_act_until_read_only(self):
        assert agents_may_act(S.CURRENT)
        assert agents_may_act(S.PAST_DUE)
        assert agents_may_act(S.GRACE)
        assert not agents_may_act(S.READ_ONLY)
        assert not agents_may_act(S.SUSPENDED)

    def test_read_only_and_suspended_flags(self):
        assert is_read_only(S.READ_ONLY) and not is_read_only(S.GRACE)
        assert is_suspended(S.SUSPENDED) and not is_suspended(S.READ_ONLY)


class TestReadOnlyGate:
    """The middleware policy: what a read-only tenant may still POST to."""

    def test_pay_export_auth_allowed_agent_actions_blocked(self):
        from src.common.middleware import _read_only_allows
        # Recovery paths stay open — the tenant can pay + export.
        assert _read_only_allows("/api/v1/billing/pay")
        assert _read_only_allows("/api/v1/credits/topup")
        assert _read_only_allows("/api/v1/auth/refresh")
        assert _read_only_allows("/api/v1/tenant/export")
        # Agent-facing mutations are blocked.
        assert not _read_only_allows("/api/v1/ai/onboarding/activate")
        assert not _read_only_allows("/api/v1/ai/signals")
