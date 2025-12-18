from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.database import get_db
from src.auth.dependencies import get_current_user, RoleChecker
from src.auth.schemas import UserResponse
from src.auth.models import User

from .service import BillingService
from .schemas import (
    SystemRateCreate, SystemRateUpdate, SystemRateResponse,
    PartnerRateCreate, PartnerRateUpdate, PartnerRateResponse,
    LedgerEntryResponse,
    InvoiceCreate, InvoiceResponse,
    SubscriptionCreate, SubscriptionUpdate, SubscriptionResponse,
    UsageReport, PartnerEarningsReport
)

router = APIRouter(prefix="/billing", tags=["billing"])

# ============= System Rate Endpoints (App Admin Only) =============

@router.post("/system-rates", response_model=SystemRateResponse, status_code=status.HTTP_201_CREATED)
async def create_system_rate(
    rate_in: SystemRateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["app_admin"]))
):
    """Create a new system rate (App Admin only)"""
    service = BillingService(db)
    return await service.create_system_rate(rate_in)

@router.get("/system-rates", response_model=List[SystemRateResponse])
async def list_system_rates(
    active_only: bool = Query(True, description="Filter active rates only"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all system rates"""
    service = BillingService(db)
    return await service.get_system_rates(active_only=active_only)

@router.get("/system-rates/{rate_id}", response_model=SystemRateResponse)
async def get_system_rate(
    rate_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get system rate by ID"""
    service = BillingService(db)
    rate = await service.get_system_rate(rate_id)
    if not rate:
        raise HTTPException(status_code=404, detail="System rate not found")
    return rate

@router.put("/system-rates/{rate_id}", response_model=SystemRateResponse)
async def update_system_rate(
    rate_id: UUID,
    rate_update: SystemRateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["app_admin"]))
):
    """Update system rate (App Admin only)"""
    service = BillingService(db)
    rate = await service.update_system_rate(rate_id, rate_update)
    if not rate:
        raise HTTPException(status_code=404, detail="System rate not found")
    return rate

# ============= Partner Rate Endpoints =============

@router.post("/partner-rates", response_model=PartnerRateResponse, status_code=status.HTTP_201_CREATED)
async def create_partner_rate(
    rate_in: PartnerRateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new partner rate"""
    service = BillingService(db)
    try:
        return await service.create_partner_rate(rate_in)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/partner-rates", response_model=List[PartnerRateResponse])
async def list_partner_rates(
    partner_id: Optional[UUID] = Query(None, description="Filter by partner ID"),
    active_only: bool = Query(True, description="Filter active rates only"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List partner rates (filtered by partner for non-admins)"""
    service = BillingService(db)
    
    # If partner_id not provided and user is not admin, use their tenant's partner
    if not partner_id:
        # Get tenant's partner_id
        from src.auth.models import Tenant
        from sqlalchemy import select
        result = await db.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if tenant and tenant.partner_id:
            partner_id = tenant.partner_id
        else:
            # No partner, return empty list
            return []
    
    return await service.get_partner_rates(partner_id, active_only=active_only)

@router.get("/partner-rates/{rate_id}", response_model=PartnerRateResponse)
async def get_partner_rate(
    rate_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get partner rate by ID"""
    service = BillingService(db)
    rate = await service.get_partner_rate(rate_id)
    if not rate:
        raise HTTPException(status_code=404, detail="Partner rate not found")
    return rate

@router.put("/partner-rates/{rate_id}", response_model=PartnerRateResponse)
async def update_partner_rate(
    rate_id: UUID,
    rate_update: PartnerRateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update partner rate"""
    service = BillingService(db)
    try:
        rate = await service.update_partner_rate(rate_id, rate_update)
        if not rate:
            raise HTTPException(status_code=404, detail="Partner rate not found")
        return rate
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ============= Ledger Entry Endpoints (Read-Only) =============

@router.get("/ledger", response_model=List[LedgerEntryResponse])
async def list_ledger_entries(
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    limit: int = Query(100, le=1000, description="Max number of entries"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List ledger entries (filtered by tenant for non-admins)"""
    service = BillingService(db)
    
    # Non-admin users can only see their tenant's entries
    tenant_id = current_user.tenant_id
    
    return await service.get_ledger_entries(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )

# ============= Reporting Endpoints =============

@router.get("/usage-report", response_model=UsageReport)
async def get_usage_report(
    start_date: datetime = Query(..., description="Report start date"),
    end_date: datetime = Query(..., description="Report end date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get usage report for current tenant"""
    service = BillingService(db)
    return await service.get_usage_report(
        tenant_id=current_user.tenant_id,
        start_date=start_date,
        end_date=end_date
    )

@router.get("/partner-earnings", response_model=PartnerEarningsReport)
async def get_partner_earnings(
    partner_id: UUID = Query(..., description="Partner ID"),
    start_date: datetime = Query(..., description="Report start date"),
    end_date: datetime = Query(..., description="Report end date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["app_admin", "partner_admin"]))
):
    """Get partner earnings report (Partner Admin or App Admin only)"""
    service = BillingService(db)
    return await service.get_partner_earnings(
        partner_id=partner_id,
        start_date=start_date,
        end_date=end_date
    )

# ============= Invoice Endpoints =============

@router.post("/invoices", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def generate_invoice(
    invoice_in: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["app_admin", "partner_admin"]))
):
    """Generate an invoice for a tenant"""
    service = BillingService(db)
    return await service.generate_invoice(invoice_in)

@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get invoice by ID"""
    service = BillingService(db)
    invoice = await service.get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # Check access: user must be from the tenant or an admin
    if invoice.tenant_id != current_user.tenant_id and current_user.role not in ["app_admin", "partner_admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return invoice

# ============= Subscription Endpoints =============

@router.post("/subscriptions", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    sub_in: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["app_admin", "partner_admin"]))
):
    """Create a new subscription"""
    service = BillingService(db)
    return await service.create_subscription(sub_in)

@router.get("/subscriptions/me", response_model=SubscriptionResponse)
async def get_my_subscription(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current user's tenant subscription"""
    service = BillingService(db)
    subscription = await service.get_subscription(current_user.tenant_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")
    return subscription

@router.put("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: UUID,
    sub_update: SubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["app_admin", "partner_admin"]))
):
    """Update subscription"""
    service = BillingService(db)
    subscription = await service.update_subscription(subscription_id, sub_update)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return subscription
    return subscription

# ============= Stripe Integration =============

from fastapi import Request
from .stripe_service import stripe_service

@router.post("/create-checkout-session")
async def create_checkout_session(
    price_id: str,
    current_user: User = Depends(get_current_user)
):
    """Create a Stripe Checkout session for subscription"""
    # Ensure customer exists
    # This is a simplified flow. In production, check DB for existing customer ID.
    customer = await stripe_service.create_customer(
        email=current_user.email,
        name=current_user.full_name,
        tenant_id=str(current_user.tenant_id)
    )
    
    # Create subscription (simplified, normally checkout session handles this)
    # For this gap analysis implementation, we'll just return a mock URL or intent
    # But let's use the service method we created
    subscription = await stripe_service.create_subscription(customer.id, price_id)
    
    return {"subscription_id": subscription.id, "client_secret": subscription.latest_invoice.payment_intent.client_secret}

@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Stripe webhooks"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    event = await stripe_service.construct_event(payload, sig_header)
    
    # Handle specific events
    if event["type"] == "invoice.payment_failed":
        # Trigger dunning logic
        invoice_data = event["data"]["object"]
        invoice_id = invoice_data["id"]
        customer_id = invoice_data["customer"]
        amount = invoice_data["amount_due"] / 100  # Convert from cents
        attempt_count = invoice_data.get("attempt_count", 1)
        
        # Get customer email from Stripe metadata or customer object
        # In a real implementation, we'd fetch the customer from Stripe
        # For now, we'll log and send a generic email
        
        from src.common.email import email_service
        
        # Get tenant from customer metadata (assuming we stored tenant_id in Stripe customer metadata)
        # For this implementation, we'll just log
        print(f"Dunning: Payment failed for invoice {invoice_id}. Amount: ${amount}, Attempt: {attempt_count}")
        
        # Update invoice status in DB (if we're tracking invoices locally)
        # For now, just trigger email
        # email_service.send_dunning_email(customer_email, invoice_id, str(amount), attempt_count)
        
        # Log for now since we don't have the customer email readily available
        print(f"Would send dunning email for invoice {invoice_id} to customer {customer_id}")
        
    elif event["type"] == "invoice.payment_succeeded":
        invoice_data = event["data"]["object"]
        invoice_id = invoice_data["id"]
        print(f"Payment succeeded for invoice {invoice_id}")
        # TODO: Update invoice status in DB
        
    return {"status": "success"}
