"""Inc 2 / TRUST — what computes days_past_due for C5's ladder.

C5 shipped the ladder, the column, the middleware, and the signals but nothing
drove them. `days_past_due` is that missing input, and it deliberately needs no
new column: a successful charge moves `next_billing_date` forward (→ 0, and the
ladder recovers the tenant), a failed one leaves it behind (→ days accumulate).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.ai.trust.dunning import SubscriptionStatus, status_for_days_past_due
from src.billing.cron_service import days_past_due

NOW = datetime(2026, 7, 22, 12, 0, 0)


class TestDaysPastDue:
    def test_future_billing_date_is_current(self):
        assert days_past_due("active", NOW + timedelta(days=5), NOW) == 0

    def test_no_billing_date_is_current(self):
        """A subscription that has never been billed is not behind."""
        assert days_past_due("active", None, NOW) == 0

    def test_overdue_counts_whole_days(self):
        assert days_past_due("past_due", NOW - timedelta(days=9), NOW) == 9

    def test_cancelled_is_never_dunned(self):
        """They left — they are not behind on anything."""
        assert days_past_due("cancelled", NOW - timedelta(days=90), NOW) == 0

    def test_exactly_due_is_not_yet_late(self):
        assert days_past_due("active", NOW, NOW) == 0

    def test_partial_day_is_not_a_day(self):
        assert days_past_due("past_due", NOW - timedelta(hours=20), NOW) == 0


class TestFeedsTheLadder:
    """The point of the computation: it lands a tenant on the right rung."""

    @pytest.mark.parametrize("days_late,expected", [
        (0, SubscriptionStatus.CURRENT),
        (1, SubscriptionStatus.PAST_DUE),
        (5, SubscriptionStatus.GRACE),
        (10, SubscriptionStatus.READ_ONLY),
        (20, SubscriptionStatus.SUSPENDED),
    ])
    def test_billing_date_maps_to_a_rung(self, days_late, expected):
        overdue = days_past_due("past_due", NOW - timedelta(days=days_late), NOW)
        assert status_for_days_past_due(overdue) == expected

    def test_a_successful_charge_recovers_the_tenant(self):
        """The monthly job advances next_billing_date — that alone un-duns them."""
        overdue = days_past_due("active", NOW + timedelta(days=30), NOW)
        assert status_for_days_past_due(overdue) == SubscriptionStatus.CURRENT
