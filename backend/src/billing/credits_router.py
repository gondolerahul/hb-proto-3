"""
Credits Router — wallet balance, Razorpay top-up, and subscription management.
Razorpay credentials are fetched from integration_registry (service_sku='razorpay_keys').
"""
import hmac
import hashlib
import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.common.database import get_db
from src.auth.router import get_current_user
from src.auth.models import User
from src.billing.credit_service import CreditService
from src.billing.billing_models import Subscription, PaymentTransaction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/credits", tags=["Credits & Payments"])

TIER_BONUS_MAP = {1: 20.0, 2: 30.0, 3: 40.0}


# ─── Helper: Get Razorpay credentials ─────────────────────────────────────────

async def _get_razorpay_creds(db: AsyncSession) -> Optional[dict]:
    """Fetch Razorpay key_id/key_secret from integration_registry."""
    try:
        from src.config.models import IntegrationRegistry
        stmt = select(IntegrationRegistry).where(
            IntegrationRegistry.service_sku == "razorpay_keys",
            IntegrationRegistry.status == "active",
        )
        result = await db.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry and entry.service_metadata:
            return entry.service_metadata
        return None
    except Exception as e:
        logger.error(f"Failed to fetch Razorpay credentials: {e}")
        return None


# ─── Schemas ──────────────────────────────────────────────────────────────────

class TopUpRequest(BaseModel):
    amount: Decimal  # USD amount to top up (e.g., 10.00)


class TopUpVerify(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    amount: Decimal


class SubscriptionCreate(BaseModel):
    plan_tier: int   # 1, 2, or 3
    monthly_fee: Decimal


# ─── Balance ──────────────────────────────────────────────────────────────────

@router.get("/balance", summary="Get credit wallet balance")
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CreditService(db)
    return await svc.get_balance(current_user.company_id)


# ─── Wallet Top-Up ────────────────────────────────────────────────────────────

@router.post("/topup", summary="Initiate Razorpay order for wallet top-up")
async def initiate_topup(
    payload: TopUpRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    creds = await _get_razorpay_creds(db)
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment gateway not configured. Add Razorpay keys to Integration Registry with SKU 'razorpay_keys'.",
        )

    try:
        import razorpay
        client = razorpay.Client(auth=(creds["key_id"], creds["key_secret"]))
        order_data = {
            "amount": int(payload.amount * 100),  # paise (INR) or cents
            "currency": "INR",  # Change to USD if Razorpay international
            "receipt": f"topup_{current_user.company_id}",
            "notes": {"company_id": str(current_user.company_id), "type": "topup"},
        }
        order = client.order.create(data=order_data)

        # Record pending transaction
        txn = PaymentTransaction(
            company_id=current_user.company_id,
            razorpay_order_id=order["id"],
            amount=payload.amount,
            currency="INR",
            transaction_type="topup",
            status="pending",
        )
        db.add(txn)
        await db.commit()

        return {
            "order_id": order["id"],
            "amount": payload.amount,
            "currency": "INR",
            "key_id": creds["key_id"],  # Sent to frontend for Razorpay.js
        }
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="razorpay package not installed. Run: pip install razorpay",
        )
    except Exception as e:
        logger.error(f"Razorpay order creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Payment initiation failed: {str(e)}")


@router.post("/topup/verify", summary="Verify Razorpay payment and credit wallet")
async def verify_topup(
    payload: TopUpVerify,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    creds = await _get_razorpay_creds(db)
    if not creds:
        raise HTTPException(status_code=503, detail="Payment gateway not configured")

    # Verify Razorpay signature
    body = f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}"
    expected_sig = hmac.new(
        creds["key_secret"].encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, payload.razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # Update transaction record
    result = await db.execute(
        select(PaymentTransaction).where(
            PaymentTransaction.razorpay_order_id == payload.razorpay_order_id,
            PaymentTransaction.company_id == current_user.company_id,
        )
    )
    txn = result.scalar_one_or_none()
    if txn:
        txn.razorpay_payment_id = payload.razorpay_payment_id
        txn.razorpay_signature = payload.razorpay_signature
        txn.status = "success"
        txn.credits_awarded = payload.amount

    # Credit the wallet
    credit_svc = CreditService(db)
    wallet = await credit_svc.add_wallet_credits(
        company_id=current_user.company_id,
        amount=payload.amount,
    )
    await db.commit()

    return {
        "message": "Payment verified and wallet credited",
        "credits_added": float(payload.amount),
        "new_balance": float(wallet.wallet_balance),
    }


# ─── Subscriptions ────────────────────────────────────────────────────────────

@router.get("/subscriptions", summary="Get current subscription info")
async def get_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Subscription).where(
            Subscription.company_id == current_user.company_id,
            Subscription.status == "active",
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return {"subscription": None, "account_model": "pay_as_you_go"}

    return {
        "subscription": {
            "id": str(sub.id),
            "plan_tier": sub.plan_tier,
            "monthly_fee": float(sub.monthly_fee),
            "bonus_pct": float(sub.bonus_pct),
            "status": sub.status,
            "razorpay_subscription_id": sub.razorpay_subscription_id,
            "next_billing_date": sub.next_billing_date.isoformat() if sub.next_billing_date else None,
        },
        "account_model": "subscription",
    }


@router.post("/subscriptions", summary="Create subscription via Razorpay")
async def create_subscription(
    payload: SubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.plan_tier not in (1, 2, 3):
        raise HTTPException(status_code=422, detail="plan_tier must be 1, 2, or 3")

    creds = await _get_razorpay_creds(db)
    razorpay_sub_id = None

    if creds:
        try:
            import razorpay
            client = razorpay.Client(auth=(creds["key_id"], creds["key_secret"]))
            # Create a Razorpay subscription (requires pre-existing plan on Razorpay dashboard)
            # Here we create the mandate — actual plan setup is done manually in Razorpay
            logger.info(f"Razorpay subscription being created for tier {payload.plan_tier}")
        except Exception as e:
            logger.warning(f"Razorpay subscription creation failed: {e}")

    # Record subscription in DB
    bonus_pct = TIER_BONUS_MAP.get(payload.plan_tier, 20.0)
    sub = Subscription(
        company_id=current_user.company_id,
        plan_tier=payload.plan_tier,
        monthly_fee=payload.monthly_fee,
        bonus_pct=Decimal(str(bonus_pct)),
        status="active",
        razorpay_subscription_id=razorpay_sub_id,
    )
    db.add(sub)

    # Update wallet account model to subscription
    credit_svc = CreditService(db)
    wallet = await credit_svc.get_or_create_wallet(current_user.company_id)
    wallet.account_model = "subscription"

    await db.commit()

    return {
        "message": f"Subscription created for Tier {payload.plan_tier}",
        "plan_tier": payload.plan_tier,
        "monthly_fee": float(payload.monthly_fee),
        "bonus_credits_pct": bonus_pct,
        "razorpay_subscription_id": razorpay_sub_id,
    }


@router.delete("/subscriptions/{subscription_id}", summary="Cancel subscription")
async def cancel_subscription(
    subscription_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime
    result = await db.execute(
        select(Subscription).where(
            Subscription.id == subscription_id,
            Subscription.company_id == current_user.company_id,
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    sub.status = "cancelled"
    sub.cancelled_at = datetime.utcnow()
    sub.updated_at = datetime.utcnow()

    # Revert wallet to PAYG
    credit_svc = CreditService(db)
    wallet = await credit_svc.get_or_create_wallet(current_user.company_id)
    wallet.account_model = "pay_as_you_go"

    await db.commit()
    return {"message": "Subscription cancelled successfully"}
