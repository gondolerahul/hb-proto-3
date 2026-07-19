"""loop/wallet_holds.py — cash reservations that close the E3 race (§23.3).

A run is admitted by placing a **hold** against *available* balance in one
short ``SELECT … FOR UPDATE`` transaction on the wallet row — so two runs
racing a wallet that can fund only one can no longer both pass a bare
threshold check and overspend. During the run, steps consume against the hold;
mid-run exhaustion finishes the current step, then suspends with a bounded
``wallet_debt``. Settlement releases the residual; actuals go to the CostLedger
as today.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.loop.models import HoldStatus, WalletHold
from src.billing.billing_models import CreditWallet
from src.billing.credit_service import (
    DEFAULT_MINIMUM_THRESHOLD,
    MINIMUM_EXECUTION_THRESHOLDS,
    CreditService,
    InsufficientCreditsError,
)

logger = logging.getLogger(__name__)

__all__ = ["hold_amount_for", "place_hold", "settle_hold", "record_graceful_debt", "HOLD_TIER_CAPS"]

# Per-tier hold ceiling so a wild planner estimate can't lock the whole wallet
# (decision 2026-07-19: PROCESS $5). Floor is the shipped tier minimum.
HOLD_TIER_CAPS = {
    "PROCESS": Decimal("5.00"),
    "AGENT": Decimal("1.00"),
    "SKILL": Decimal("0.50"),
    "ACTION": Decimal("0.20"),
    "LOOP": Decimal("0"),   # Loops create no runs → no hold (§17.4)
}


def hold_amount_for(entity_type: str, planner_estimate: Optional[Decimal]) -> Decimal:
    """hold = clamp(estimate, tier_minimum, tier_cap) — decision 2026-07-19."""
    et = entity_type.upper()
    floor = MINIMUM_EXECUTION_THRESHOLDS.get(et, DEFAULT_MINIMUM_THRESHOLD)
    cap = HOLD_TIER_CAPS.get(et, Decimal("5.00"))
    est = planner_estimate if planner_estimate and planner_estimate > 0 else floor
    return max(floor, min(est, cap))


def _locked_available(wallet: Any, now: datetime) -> Decimal:
    """Total spendable across buckets, read from an already-locked wallet row.

    Mirrors CreditService.get_balance's bucket/expiry logic but is side-effect
    free (no daily-credit injection, no commit) so it is safe to call under the
    admission ``FOR UPDATE`` lock.
    """
    total = Decimal("0")
    daily_exp = getattr(wallet, "daily_expires_at", None)
    if daily_exp is not None and daily_exp >= now:
        total += Decimal(str(wallet.daily_credits or 0))
    wal_exp = getattr(wallet, "wallet_expires_at", None)
    if wal_exp is None or wal_exp >= now:
        total += Decimal(str(wallet.wallet_balance or 0))
    sub_exp = getattr(wallet, "sub_credits_expire_at", None)
    if sub_exp is None or sub_exp >= now:
        total += Decimal(str(wallet.subscription_credits or 0))
        total += Decimal(str(wallet.subscription_bonus_credits or 0))
    return total


async def _active_holds_total(db: AsyncSession, company_id: uuid.UUID) -> Decimal:
    """Unspent reserved cash across a company's ACTIVE holds."""
    total = (await db.execute(
        select(func.coalesce(func.sum(WalletHold.amount_held - WalletHold.amount_spent), 0))
        .where(WalletHold.company_id == company_id,
               WalletHold.status == HoldStatus.ACTIVE)
    )).scalar_one()
    return Decimal(str(total or 0))


async def place_hold(
    db: AsyncSession, company_id: uuid.UUID, run_id: uuid.UUID,
    entity_type: str, planner_estimate: Optional[Decimal] = None,
) -> WalletHold:
    """Admit a run by reserving cash. Raises InsufficientCreditsError if the
    *available* balance (total − active holds − debt) can't cover the hold.

    The wallet row is locked ``FOR UPDATE`` for the whole check-and-reserve, so
    concurrent admissions serialise — the E3 race cannot oversubscribe.
    """
    amount = hold_amount_for(entity_type, planner_estimate)

    # Idempotency: a re-admitted run (arq retry) keeps its existing hold.
    existing = (await db.execute(
        select(WalletHold).where(WalletHold.run_id == run_id)
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    # Ensure a wallet exists (this may commit), THEN lock it for the admission
    # window. Balance is computed from the *locked* row — never via get_balance,
    # whose daily-credit auto-injection commits and would release the lock
    # mid-admission, re-opening the E3 race.
    await CreditService(db).get_or_create_wallet(company_id)
    wallet = (await db.execute(
        select(CreditWallet).where(CreditWallet.company_id == company_id)
        .with_for_update()
    )).scalar_one()

    total_available = _locked_available(wallet, datetime.utcnow())
    reserved = await _active_holds_total(db, company_id)
    debt = Decimal(str(getattr(wallet, "wallet_debt", 0) or 0))
    available = total_available - reserved - debt

    if available < amount:
        raise InsufficientCreditsError(
            f"Cannot admit run: available ${available:.4f} "
            f"(balance ${total_available:.4f} − holds ${reserved:.4f} − debt ${debt:.4f}) "
            f"below the ${amount:.4f} hold for entity type '{entity_type}'."
        )

    hold = WalletHold(
        company_id=company_id, run_id=run_id,
        amount_held=amount, amount_spent=Decimal("0"), status=HoldStatus.ACTIVE,
    )
    db.add(hold)
    await db.flush()
    return hold


async def settle_hold(
    db: AsyncSession, run_id: uuid.UUID, actual_spent: Decimal,
) -> Optional[WalletHold]:
    """Release the residual hold at run finalize; record the actual spend.

    The actual cost is already written to the CostLedger / run.total_cost_usd by
    the shipped billing path — the hold is a *reservation*, so settlement just
    marks it done and frees the unspent remainder for other runs.
    """
    hold = (await db.execute(
        select(WalletHold).where(WalletHold.run_id == run_id).with_for_update()
    )).scalar_one_or_none()
    if hold is None:
        return None
    hold.amount_spent = Decimal(str(actual_spent))
    hold.status = HoldStatus.SETTLED
    hold.settled_at = datetime.utcnow()
    await db.flush()
    return hold


async def record_graceful_debt(
    db: AsyncSession, company_id: uuid.UUID, run_id: uuid.UUID, overage: Decimal,
) -> Decimal:
    """Mid-run exhaustion (§23.3): record bounded debt = min(overage, cap),
    cap = max($1, 5% of the hold). Returns the debt actually recorded.

    The run has completed its current step cleanly and will suspend
    (PAUSED, insufficient_funds); the debt settles from the next top-up before
    any new spending.
    """
    hold = (await db.execute(
        select(WalletHold).where(WalletHold.run_id == run_id).with_for_update()
    )).scalar_one_or_none()
    cap = Decimal("1.00")
    if hold is not None:
        cap = max(Decimal("1.00"), (Decimal(str(hold.amount_held)) * Decimal("0.05")))
        hold.status = HoldStatus.EXHAUSTED
    debt = min(Decimal(str(overage)), cap)
    wallet = (await db.execute(
        select(CreditWallet).where(CreditWallet.company_id == company_id).with_for_update()
    )).scalar_one_or_none()
    if wallet is not None:
        # CreditWallet is a legacy Column-style model; setattr sidesteps the
        # Column[Decimal] descriptor typing while writing a real Decimal.
        setattr(wallet, "wallet_debt",
                Decimal(str(getattr(wallet, "wallet_debt", 0) or 0)) + debt)
    await db.flush()
    return debt
