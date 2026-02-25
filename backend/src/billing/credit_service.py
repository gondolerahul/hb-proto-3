"""
Credit Service — manages credit wallet consumption with priority ordering.

Priority order:
  1. Daily credits (always first, universal)
  2a. Pay-As-You-Go: Wallet balance
  2b. Subscription: Subscription credits + bonus credits

Raises InsufficientCreditsError if all buckets are zero.
"""
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.billing.billing_models import CreditWallet, Subscription


class InsufficientCreditsError(Exception):
    """Raised when all credit buckets are exhausted and task execution should be blocked."""
    pass


DAILY_CREDIT_AMOUNT = Decimal("5.00")


class CreditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_wallet(self, company_id: UUID) -> CreditWallet:
        """Return credit wallet for company, creating with $5 daily credit if not found."""
        stmt = select(CreditWallet).where(CreditWallet.company_id == company_id)
        result = await self.db.execute(stmt)
        wallet = result.scalar_one_or_none()

        if not wallet:
            tomorrow = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow = tomorrow + timedelta(days=1)
            wallet = CreditWallet(
                company_id=company_id,
                daily_credits=DAILY_CREDIT_AMOUNT,
                daily_expires_at=tomorrow,
            )
            self.db.add(wallet)
            await self.db.commit()
            await self.db.refresh(wallet)

        return wallet

    async def get_balance(self, company_id: UUID) -> dict:
        """Return current credit balance across all buckets."""
        wallet = await self.get_or_create_wallet(company_id)
        now = datetime.utcnow()

        # Check if daily credits expired
        daily = Decimal(str(wallet.daily_credits))
        if wallet.daily_expires_at and wallet.daily_expires_at < now:
            daily = Decimal("0")

        # Check wallet balance expiry
        wallet_bal = Decimal(str(wallet.wallet_balance))
        if wallet.wallet_expires_at and wallet.wallet_expires_at < now:
            wallet_bal = Decimal("0")

        # Check subscription credits expiry
        sub_credits = Decimal(str(wallet.subscription_credits))
        sub_bonus = Decimal(str(wallet.subscription_bonus_credits))
        if wallet.sub_credits_expire_at and wallet.sub_credits_expire_at < now:
            sub_credits = Decimal("0")
            sub_bonus = Decimal("0")

        return {
            "account_model": wallet.account_model,
            "daily_credits": float(daily),
            "daily_expires_at": wallet.daily_expires_at.isoformat() if wallet.daily_expires_at else None,
            "wallet_balance": float(wallet_bal),
            "wallet_expires_at": wallet.wallet_expires_at.isoformat() if wallet.wallet_expires_at else None,
            "subscription_credits": float(sub_credits),
            "subscription_bonus_credits": float(sub_bonus),
            "sub_credits_expire_at": wallet.sub_credits_expire_at.isoformat() if wallet.sub_credits_expire_at else None,
            "total_available": float(daily + wallet_bal + sub_credits + sub_bonus),
        }

    async def consume(self, company_id: UUID, amount: Decimal) -> dict:
        """
        Deduct `amount` from credit buckets in priority order.
        Returns dict showing how much was deducted from each bucket.

        Raises InsufficientCreditsError if total available < amount.
        """
        wallet = await self.get_or_create_wallet(company_id)
        now = datetime.utcnow()
        remaining = amount
        deductions = {"daily": Decimal("0"), "wallet": Decimal("0"), "subscription": Decimal("0")}

        # Check expiry and zero expired balances in-place
        if wallet.daily_expires_at and wallet.daily_expires_at < now:
            wallet.daily_credits = Decimal("0")
        if wallet.wallet_expires_at and wallet.wallet_expires_at < now:
            wallet.wallet_balance = Decimal("0")
        if wallet.sub_credits_expire_at and wallet.sub_credits_expire_at < now:
            wallet.subscription_credits = Decimal("0")
            wallet.subscription_bonus_credits = Decimal("0")

        total_available = (
            Decimal(str(wallet.daily_credits))
            + Decimal(str(wallet.wallet_balance))
            + Decimal(str(wallet.subscription_credits))
            + Decimal(str(wallet.subscription_bonus_credits))
        )

        if total_available < amount:
            raise InsufficientCreditsError(
                f"Insufficient credits. Required: ${amount}, Available: ${total_available}"
            )

        # 1. Consume daily credits first
        daily = Decimal(str(wallet.daily_credits))
        if remaining > 0 and daily > 0:
            take = min(remaining, daily)
            wallet.daily_credits = daily - take
            deductions["daily"] = take
            remaining -= take

        # 2a. PAYG — consume wallet balance
        if remaining > 0 and wallet.account_model == "pay_as_you_go":
            bal = Decimal(str(wallet.wallet_balance))
            if bal > 0:
                take = min(remaining, bal)
                wallet.wallet_balance = bal - take
                deductions["wallet"] = take
                remaining -= take

        # 2b. Subscription — consume subscription credits then bonus
        elif remaining > 0 and wallet.account_model == "subscription":
            sub = Decimal(str(wallet.subscription_credits))
            if sub > 0:
                take = min(remaining, sub)
                wallet.subscription_credits = sub - take
                deductions["subscription"] += take
                remaining -= take

            bonus = Decimal(str(wallet.subscription_bonus_credits))
            if remaining > 0 and bonus > 0:
                take = min(remaining, bonus)
                wallet.subscription_bonus_credits = bonus - take
                deductions["subscription"] += take
                remaining -= take

        wallet.updated_at = datetime.utcnow()
        await self.db.commit()
        return deductions

    async def add_wallet_credits(
        self,
        company_id: UUID,
        amount: Decimal,
        validity_days: int = 365,
    ) -> CreditWallet:
        """Credit the wallet balance bucket (PAYG top-up)."""
        wallet = await self.get_or_create_wallet(company_id)
        wallet.wallet_balance = Decimal(str(wallet.wallet_balance)) + amount
        wallet.wallet_expires_at = datetime.utcnow() + timedelta(days=validity_days)
        wallet.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet

    async def inject_subscription_credits(
        self,
        company_id: UUID,
        base_amount: Decimal,
        bonus_pct: Decimal,
    ) -> CreditWallet:
        """
        Replace subscription credits (no carry-forward).
        Called on the 1st of each month by the cron job.
        """
        wallet = await self.get_or_create_wallet(company_id)
        bonus = base_amount * (bonus_pct / Decimal("100"))

        # Flush old credits — strict no carry-forward
        wallet.subscription_credits = base_amount
        wallet.subscription_bonus_credits = bonus
        wallet.account_model = "subscription"

        # Expire at end of this month
        now = datetime.utcnow()
        import calendar
        last_day = calendar.monthrange(now.year, now.month)[1]
        wallet.sub_credits_expire_at = datetime(now.year, now.month, last_day, 23, 59, 59)
        wallet.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet

    async def flush_and_inject_daily_credits(self, company_id: UUID) -> CreditWallet:
        """
        Flush expired daily credits and inject fresh $5.
        Called daily at 00:00:00 by cron job.
        """
        wallet = await self.get_or_create_wallet(company_id)
        wallet.daily_credits = DAILY_CREDIT_AMOUNT
        tomorrow = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = tomorrow + timedelta(days=1)
        wallet.daily_expires_at = tomorrow
        wallet.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet

    async def require_credits(self, company_id: UUID, amount: Decimal) -> None:
        """
        Middleware helper — raises HTTP 402 if insufficient credits.
        Use before processing billable tasks.
        """
        balance = await self.get_balance(company_id)
        if balance["total_available"] < float(amount):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"Insufficient credits. Required: ${amount:.4f}, "
                    f"Available: ${balance['total_available']:.4f}. "
                    "Please top up your wallet or check your subscription."
                )
            )
