"""DRIVER D2 — the per-path cost estimator's pure parts (11_driver.md §4).

The design's own list of what would violate it, each pinned here where it
is pinnable without a database: a platform-wide fallback and the company
scope live in the DB tests; **summing bases**, **placeholder currency**
and the **observation floor** are properties of pure functions and are
pinned as such.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from src.ai.genui.cost import (
    OBSERVATION_FLOOR,
    estimate_from_observations,
)
from src.ai.genui.trays import compose_tray
from src.ai.orm.execution import HumanApproval

APPROVAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _approval(snapshot: dict[str, Any]) -> HumanApproval:
    return HumanApproval(
        id=APPROVAL_ID,
        run_id=uuid.uuid4(),
        checkpoint_trigger="policy:x",
        checkpoint_key=str(snapshot.get("checkpoint_key") or "before_external_communication"),
        status="PENDING",
        requested_at=datetime(2026, 7, 29, 12, 0, 0),
        context_snapshot=snapshot,
    )


NOW = datetime(2026, 7, 29, 12, 30, 0)


# ── the pure estimator ───────────────────────────────────────────────────────

def test_below_the_floor_is_none_at_the_floor_is_an_estimate() -> None:
    four = [Decimal(10)] * (OBSERVATION_FLOOR - 1)
    five = [Decimal(10)] * OBSERVATION_FLOOR
    assert estimate_from_observations(four) is None
    assert estimate_from_observations(five) is not None


def test_the_estimate_is_the_median_not_the_mean() -> None:
    # One expensive outlier must not drag the figure — that is the point
    # of a median for "what does this kind of decision usually cost".
    spends = [Decimal(2), Decimal(3), Decimal(4), Decimal(5), Decimal(500)]
    estimate = estimate_from_observations(spends)
    assert estimate is not None
    assert estimate["amount"] == 4.0


def test_zero_spend_approvals_are_real_observations() -> None:
    # Excluding them would bias every estimate upward.
    spends = [Decimal(0), Decimal(0), Decimal(0), Decimal(10), Decimal(20)]
    estimate = estimate_from_observations(spends)
    assert estimate is not None
    assert estimate["amount"] == 0.0


def test_the_basis_names_the_denominator_and_currency_is_never_guessed() -> None:
    estimate = estimate_from_observations([Decimal(7)] * 6)
    assert estimate is not None
    assert estimate["currency"] is None
    assert "observed" in estimate["basis"]
    assert "6" in estimate["basis"]


# ── the composer interplay (never summed, gate's number wins) ────────────────

OBSERVED = {"amount": 12.5, "currency": None, "basis": "observed: median platform spend across 5 similar decisions"}


def test_the_gates_own_amount_always_wins_and_is_never_summed() -> None:
    tray = compose_tray(
        approval=_approval({
            "category": "outbound_payout", "reason": "r", "band": 2,
            "amount": 84200.0,
            "checkpoint_key": "before_outbound_payout_above_band",
        }),
        prepared_by=None, sla_seconds=None, on_timeout=None, now=NOW,
        observed_cost=OBSERVED,
    )
    approve = next(p for p in tray["paths"] if p["key"] == "approve")
    assert approve["cost"]["amount"] == 84200.0
    assert approve["cost"]["basis"] == "the amount itself"


def test_an_amountless_gate_takes_the_observed_estimate() -> None:
    tray = compose_tray(
        approval=_approval({
            "category": "email_dispatch", "reason": "r",
            "checkpoint_key": "before_external_communication",
        }),
        prepared_by=None, sla_seconds=None, on_timeout=None, now=NOW,
        observed_cost=OBSERVED,
    )
    approve = next(p for p in tray["paths"] if p["key"] == "approve")
    assert approve["cost"] == OBSERVED


def test_no_amount_and_no_estimate_stays_an_honest_null() -> None:
    tray = compose_tray(
        approval=_approval({
            "category": "email_dispatch", "reason": "r",
            "checkpoint_key": "before_external_communication",
        }),
        prepared_by=None, sla_seconds=None, on_timeout=None, now=NOW,
        observed_cost=None,
    )
    approve = next(p for p in tray["paths"] if p["key"] == "approve")
    assert approve["cost"] is None


def test_the_decline_path_never_carries_the_estimate() -> None:
    # Declining has consequences the platform cannot observe; zero or the
    # approve-side median would both be fabrications there.
    tray = compose_tray(
        approval=_approval({
            "category": "email_dispatch", "reason": "r",
            "checkpoint_key": "before_external_communication",
        }),
        prepared_by=None, sla_seconds=None, on_timeout=None, now=NOW,
        observed_cost=OBSERVED,
    )
    decline = next(p for p in tray["paths"] if p["key"] == "decline")
    assert decline["cost"] is None
