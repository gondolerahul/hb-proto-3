import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, Text, Numeric, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.common.database import Base

class SystemRate(Base):
    """System-level cost rates for resources (what the platform pays to providers)"""
    __tablename__ = "system_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_type = Column(String, nullable=False)  # text_tokens_input, text_tokens_output, voice_min_twilio, etc.
    unit = Column(String, nullable=False)  # 1k_tokens, minute, request, etc.
    rate = Column(Numeric(18, 6), nullable=False)  # Cost in USD
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    partner_rates = relationship("PartnerRate", back_populates="system_rate")

class PartnerRate(Base):
    """Partner-specific selling rates (what partners charge their tenants)"""
    __tablename__ = "partner_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_id = Column(UUID(as_uuid=True), ForeignKey("partners.id"), nullable=False)
    system_rate_id = Column(UUID(as_uuid=True), ForeignKey("system_rates.id"), nullable=False)
    rate = Column(Numeric(18, 6), nullable=False)  # Price in USD (must be >= system rate)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    partner = relationship("Partner")
    system_rate = relationship("SystemRate", back_populates="partner_rates")

class LedgerEntry(Base):
    """Immutable ledger entries recording all usage and financial calculations"""
    __tablename__ = "ledger_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    partner_id = Column(UUID(as_uuid=True), ForeignKey("partners.id"), nullable=True)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("executions.id"), nullable=True)
    
    # Resource tracking
    resource_type = Column(String, nullable=False)  # text_tokens_input, text_tokens_output, etc.
    quantity = Column(Numeric(18, 6), nullable=False)  # Number of units consumed
    unit = Column(String, nullable=False)  # 1k_tokens, minute, etc.
    
    # Financial calculations (all in USD)
    platform_cost = Column(Numeric(18, 6), nullable=False)  # What platform pays to provider
    tenant_cost = Column(Numeric(18, 6), nullable=False)  # What tenant is charged
    partner_commission = Column(Numeric(18, 6), nullable=False)  # Partner's profit (tenant_cost - platform_cost)
    
    # Metadata
    entry_metadata = Column(Text, nullable=True)  # JSON string for additional info (renamed from 'metadata' to avoid SQLAlchemy conflict)
    created_at = Column(DateTime, default=datetime.utcnow)


    tenant = relationship("Tenant")
    partner = relationship("Partner")
    execution = relationship("Execution")

class Invoice(Base):
    """Invoice generation and tracking"""
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    invoice_number = Column(String, unique=True, nullable=False)
    
    # Financial details
    total_amount = Column(Numeric(18, 6), nullable=False)  # Total amount in USD
    currency = Column(String, default="USD")
    status = Column(String, default="pending")  # pending, paid, overdue, cancelled
    
    # Date tracking
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    due_date = Column(DateTime, nullable=False)
    paid_date = Column(DateTime, nullable=True)
    
    # Metadata
    line_items = Column(Text, nullable=True)  # JSON string of line items
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant")

class Subscription(Base):
    """Tenant subscription management"""
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    # Subscription details
    plan_name = Column(String, nullable=False)  # free, basic, premium, enterprise
    status = Column(String, default="active")  # active, suspended, cancelled
    billing_cycle = Column(String, default="monthly")  # monthly, annual
    
    # Credit/balance tracking
    credit_balance = Column(Numeric(18, 6), default=0.0)  # Prepaid credits
    
    # Date tracking
    started_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant")

class PaymentMethod(Base):
    """Stored payment methods (cards, etc.)"""
    __tablename__ = "payment_methods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    stripe_payment_method_id = Column(String, unique=True, nullable=False)
    stripe_customer_id = Column(String, nullable=False)
    type = Column(String, default="card")
    last4 = Column(String, nullable=True)
    exp_month = Column(Integer, nullable=True)
    exp_year = Column(Integer, nullable=True)
    is_default = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant")

# Update Invoice with Stripe fields
Invoice.stripe_invoice_id = Column(String, nullable=True)
Invoice.payment_intent_id = Column(String, nullable=True)

# Update Subscription with Stripe fields
Subscription.stripe_subscription_id = Column(String, nullable=True)
Subscription.stripe_customer_id = Column(String, nullable=True)
