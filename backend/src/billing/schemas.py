from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

# ============= System Rate Schemas =============

class SystemRateBase(BaseModel):
    resource_type: str = Field(..., description="Resource type (e.g., text_tokens_input, voice_min_twilio)")
    unit: str = Field(..., description="Unit of measurement (e.g., 1k_tokens, minute)")
    rate: Decimal = Field(..., description="Cost in USD", ge=0)
    description: Optional[str] = None

class SystemRateCreate(SystemRateBase):
    pass

class SystemRateUpdate(BaseModel):
    rate: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = None
    description: Optional[str] = None

class SystemRateResponse(SystemRateBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ============= Partner Rate Schemas =============

class PartnerRateBase(BaseModel):
    system_rate_id: UUID
    rate: Decimal = Field(..., description="Selling price in USD", ge=0)

class PartnerRateCreate(PartnerRateBase):
    partner_id: UUID

class PartnerRateUpdate(BaseModel):
    rate: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = None

class PartnerRateResponse(PartnerRateBase):
    id: UUID
    partner_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    # Include system rate details
    system_rate: Optional[SystemRateResponse] = None

    class Config:
        from_attributes = True

# ============= Ledger Entry Schemas =============

class LedgerEntryCreate(BaseModel):
    tenant_id: UUID
    partner_id: Optional[UUID] = None
    execution_id: Optional[UUID] = None
    resource_type: str
    quantity: Decimal = Field(..., ge=0)
    unit: str
    platform_cost: Decimal = Field(..., ge=0)
    tenant_cost: Decimal = Field(..., ge=0)
    partner_commission: Decimal = Field(..., ge=0)
    entry_metadata: Optional[str] = None


    @field_validator('tenant_cost')
    @classmethod
    def validate_tenant_cost(cls, v, info):
        if 'platform_cost' in info.data and v < info.data['platform_cost']:
            raise ValueError('tenant_cost must be >= platform_cost')
        return v

    @field_validator('partner_commission')
    @classmethod
    def validate_commission(cls, v, info):
        if 'tenant_cost' in info.data and 'platform_cost' in info.data:
            expected_commission = info.data['tenant_cost'] - info.data['platform_cost']
            # Allow for small rounding differences
            if abs(v - expected_commission) > Decimal('0.000001'):
                raise ValueError(f'partner_commission must equal tenant_cost - platform_cost')
        return v

class LedgerEntryResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    partner_id: Optional[UUID]
    execution_id: Optional[UUID]
    resource_type: str
    quantity: Decimal
    unit: str
    platform_cost: Decimal
    tenant_cost: Decimal
    partner_commission: Decimal
    entry_metadata: Optional[str]
    created_at: datetime


    class Config:
        from_attributes = True

# ============= Invoice Schemas =============

class InvoiceCreate(BaseModel):
    tenant_id: UUID
    period_start: datetime
    period_end: datetime
    due_date: datetime

class InvoiceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    invoice_number: str
    total_amount: Decimal
    currency: str
    status: str
    period_start: datetime
    period_end: datetime
    due_date: datetime
    paid_date: Optional[datetime]
    line_items: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ============= Subscription Schemas =============

class SubscriptionBase(BaseModel):
    plan_name: str
    billing_cycle: str = "monthly"

class SubscriptionCreate(SubscriptionBase):
    tenant_id: UUID
    credit_balance: Decimal = Decimal('0.0')

class SubscriptionUpdate(BaseModel):
    plan_name: Optional[str] = None
    status: Optional[str] = None
    billing_cycle: Optional[str] = None
    credit_balance: Optional[Decimal] = None
    expires_at: Optional[datetime] = None

class SubscriptionResponse(SubscriptionBase):
    id: UUID
    tenant_id: UUID
    status: str
    credit_balance: Decimal
    started_at: datetime
    expires_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ============= Reporting Schemas =============

class UsageReportLine(BaseModel):
    resource_type: str
    total_quantity: Decimal
    total_cost: Decimal
    unit: str

class UsageReport(BaseModel):
    tenant_id: UUID
    period_start: datetime
    period_end: datetime
    total_cost: Decimal
    line_items: List[UsageReportLine]

class PartnerEarningsLine(BaseModel):
    tenant_id: UUID
    tenant_name: str
    total_commission: Decimal

class PartnerEarningsReport(BaseModel):
    partner_id: UUID
    period_start: datetime
    period_end: datetime
    total_earnings: Decimal
    tenants: List[PartnerEarningsLine]
