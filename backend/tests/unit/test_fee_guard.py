"""Inc 2 / TRUST — the fee-formula guard (E4).

Two claims are pinned here: a negative TB is detected (and named) rather than
silently clamped, and the discount is subtracted LAST so it never reduces the
platform or sales-partner fee. The second is the "ordering intent" half of E4 —
it is easy to "simplify" the formula into charging fees on the discounted cost,
which quietly moves who pays for a discount.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.ai.trust.fee_guard import (
    clamp_total_billing,
    inspect_fee_result,
)
from src.billing.billing_service import calculate_tb, compute_billed_amount

D = Decimal


class TestOrderingIntent:
    """The discount applies to the multiplied cost and is subtracted last."""

    def test_partner_fee_is_unaffected_by_discount(self):
        # c=100, mf=2 → multiplied 200. spf=10% → partner earns 20 either way.
        no_discount = calculate_tb(D("100"), D("2"), D("0"), D("0.10"), D("0"))
        discounted = calculate_tb(D("100"), D("2"), D("0"), D("0.10"), D("0.50"))
        assert no_discount["partner_fee_amount"] == D("20.00")
        assert discounted["partner_fee_amount"] == D("20.00")

    def test_platform_fee_is_unaffected_by_discount(self):
        no_discount = calculate_tb(D("100"), D("2"), D("0.15"), D("0"), D("0"))
        discounted = calculate_tb(D("100"), D("2"), D("0.15"), D("0"), D("0.50"))
        assert no_discount["platform_fee_amount"] == discounted["platform_fee_amount"]

    def test_discount_is_taken_on_the_multiplied_cost(self):
        tb = calculate_tb(D("100"), D("2"), D("0.15"), D("0.10"), D("0.25"))
        # multiplied 200; pf 30; spf 20; d 50 → 200 + 30 + 20 − 50 = 200
        assert tb["multiplied_cost"] == D("200")
        assert tb["discount_amount"] == D("50.00")
        assert tb["total_billing"] == D("200.00")


class TestNegativeDetection:
    def test_healthy_result_is_not_flagged(self):
        tb = calculate_tb(D("10"), D("1.5"), D("0.10"), D("0.05"), D("0.20"))
        assert tb["total_billing"] > 0
        assert inspect_fee_result(
            tb, mf=D("1.5"), pf=D("0.10"), spf=D("0.05"), d=D("0.20")) is None

    def test_zero_is_not_flagged(self):
        """A zero-cost event is legitimate — only a NEGATIVE price is a bug."""
        tb = calculate_tb(D("0"), D("1"), D("0"), D("0"), D("0"))
        assert inspect_fee_result(
            tb, mf=D("1"), pf=D("0"), spf=D("0"), d=D("0")) is None

    def test_discount_over_breakeven_is_named(self):
        # break-even is 1 + 0.10 + 0.05 = 1.15; a 1.50 discount goes negative.
        mf, pf, spf, d = D("2"), D("0.10"), D("0.05"), D("1.50")
        tb = calculate_tb(D("100"), mf, pf, spf, d)
        assert tb["total_billing"] < 0
        finding = inspect_fee_result(tb, mf=mf, pf=pf, spf=spf, d=d)
        assert finding is not None
        assert "discount_pct" in finding.reason
        assert "break-even" in finding.reason
        assert finding.total_billing == tb["total_billing"]

    def test_negative_multiplier_is_named(self):
        mf = D("-1")
        tb = calculate_tb(D("100"), mf, D("0"), D("0"), D("0"))
        finding = inspect_fee_result(tb, mf=mf, pf=D("0"), spf=D("0"), d=D("0"))
        assert finding is not None
        assert "multiplier_factor" in finding.reason

    def test_payload_is_json_safe(self):
        mf, pf, spf, d = D("2"), D("0"), D("0"), D("2")
        tb = calculate_tb(D("100"), mf, pf, spf, d)
        finding = inspect_fee_result(tb, mf=mf, pf=pf, spf=spf, d=d)
        assert finding is not None
        payload = finding.as_payload()
        assert all(isinstance(v, str) for v in payload.values())
        assert payload["discount_pct"] == "2"


class TestClamp:
    @pytest.mark.parametrize("value,expected", [
        (D("5.25"), D("5.25")), (D("0"), D("0")), (D("-0.01"), D("0")),
        (D("-100"), D("0")),
    ])
    def test_never_negative(self, value, expected):
        assert clamp_total_billing(value) == expected


class _Config:
    """Minimal stand-in for a BillingConfig row."""

    def __init__(self, mf, pf, spf, d):
        self.multiplier_factor = mf
        self.platform_fee_pct = pf
        self.sales_partner_fee_pct = spf
        self.discount_pct = d


class TestComputeBilledAmount:
    def test_misconfigured_config_bills_zero_not_a_credit(self, caplog):
        """The clamp survives — a config bug must never credit the customer."""
        config = _Config(D("2"), D("0"), D("0"), D("3"))
        with caplog.at_level("ERROR"):
            billed = compute_billed_amount(D("100"), config)
        assert billed == D("0")
        assert "E4 fee misconfiguration" in caplog.text

    def test_healthy_config_is_untouched(self):
        config = _Config(D("1.5"), D("0.10"), D("0"), D("0"))
        assert compute_billed_amount(D("10"), config) == D("16.50")

    def test_no_config_is_the_identity_formula(self):
        assert compute_billed_amount(D("7.25"), None) == D("7.25")
