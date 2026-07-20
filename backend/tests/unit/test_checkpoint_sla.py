"""Inc 2 / TRUST — the per-checkpoint HITL SLA policy (C3).

The policy is data: money/binding categories fail safe (auto_deny) with short
SLAs, outbound comms park (re-raise), high-stakes governance/HR escalate. Every
seeded checkpoint carries an SLA. The overdue-sweep behaviour is in
test_checkpoint_sla_db.py.
"""
from __future__ import annotations

import pytest

from src.ai.governance.checkpoints import (
    CHECKPOINT_SEED,
    OnTimeout,
    sla_for_category,
)


class TestPolicy:
    @pytest.mark.parametrize("category,on_timeout", [
        ("payout", OnTimeout.AUTO_DENY),
        ("refund", OnTimeout.AUTO_DENY),
        ("contract", OnTimeout.AUTO_DENY),
        ("data_deletion", OnTimeout.AUTO_DENY),
        ("email", OnTimeout.AUTO_PARK),
        ("public_statement", OnTimeout.AUTO_PARK),
        ("governance", OnTimeout.ESCALATE),
        ("employment_offer", OnTimeout.ESCALATE),
    ])
    def test_category_on_timeout(self, category, on_timeout):
        assert sla_for_category(category)[1] == on_timeout

    def test_unknown_category_escalates(self):
        assert sla_for_category("mystery")[1] == OnTimeout.ESCALATE

    def test_money_sla_is_shorter_than_comms(self):
        assert sla_for_category("payout")[0] < sla_for_category("email")[0]

    def test_every_seed_row_has_an_sla(self):
        for row in CHECKPOINT_SEED:
            assert row["sla_seconds"] > 0, row["key"]
            assert row["on_timeout"] in (
                OnTimeout.AUTO_PARK, OnTimeout.AUTO_DENY, OnTimeout.ESCALATE), row["key"]

    def test_money_categories_all_fail_safe(self):
        for cat in ("payout", "refund", "contract", "vendor_creation",
                    "price_change", "data_deletion"):
            assert sla_for_category(cat)[1] == OnTimeout.AUTO_DENY, cat
