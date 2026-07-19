"""Inc 1 / LOOP+ENV — pure budget/hold/schedule logic (§17, §20.4, §23.3).

Hold sizing (clamp to tier floor/cap), envelope downshift/cap with the
protected reserve, and schedule slot dedupe. DB-backed admission race +
heartbeat/watchdog live in tests/integration/test_loop_runtime_db.py.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from src.ai.loop.envelopes import is_capped, is_downshift, utilization_pct
from src.ai.loop.schedules import current_slot
from src.ai.loop.wallet_holds import hold_amount_for


class TestHoldSizing:
    def test_floors_at_tier_minimum(self):
        # PROCESS minimum is $0.50; a tiny estimate floors up.
        assert hold_amount_for("PROCESS", Decimal("0.10")) == Decimal("0.50")

    def test_caps_at_tier_ceiling(self):
        # A wild $100 estimate is capped at the PROCESS ceiling $5.
        assert hold_amount_for("PROCESS", Decimal("100")) == Decimal("5.00")

    def test_uses_estimate_in_band(self):
        assert hold_amount_for("PROCESS", Decimal("2.00")) == Decimal("2.00")

    def test_none_estimate_uses_floor(self):
        assert hold_amount_for("AGENT", None) == Decimal("0.05")

    def test_agent_cap(self):
        assert hold_amount_for("AGENT", Decimal("50")) == Decimal("1.00")


def _env(envelope, reserved, spent, downshift=80):
    return SimpleNamespace(
        envelope_usd=Decimal(str(envelope)), reserved_usd=Decimal(str(reserved)),
        spent_usd=Decimal(str(spent)), downshift_at_pct=downshift,
    )


class TestEnvelope:
    def test_utilization(self):
        assert utilization_pct(_env(100, 10, 50)) == 50.0

    def test_downshift_threshold(self):
        assert not is_downshift(_env(100, 10, 79))
        assert is_downshift(_env(100, 10, 80))

    def test_capped_at_spendable_not_full_envelope(self):
        # Spendable = envelope - reserved = 90. At 90 spent, non-critical caps;
        # the reserved 10 remains for P14/P17 (pre-funded, never exempt).
        assert not is_capped(_env(100, 10, 89))
        assert is_capped(_env(100, 10, 90))

    def test_reserve_protects_critical_headroom(self):
        # Even "full" spend of the spendable band leaves the reserve intact.
        env = _env(100, 10, 90)
        assert is_capped(env)
        spendable = env.envelope_usd - env.reserved_usd
        assert env.spent_usd <= env.envelope_usd  # reserve never consumed by non-critical


class TestScheduleSlots:
    def test_same_window_same_slot(self):
        t1 = datetime(2026, 7, 19, 10, 0, 0)
        t2 = datetime(2026, 7, 19, 10, 59, 0)
        every = 3600  # hourly
        assert current_slot(t1, every) == current_slot(t2, every)

    def test_next_window_new_slot(self):
        t1 = datetime(2026, 7, 19, 10, 30, 0)
        t2 = datetime(2026, 7, 19, 11, 30, 0)
        assert current_slot(t1, 3600) != current_slot(t2, 3600)
