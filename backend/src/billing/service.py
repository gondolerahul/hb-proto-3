from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from .models import SystemRate, PartnerRate, LedgerEntry, Invoice, Subscription
from .schemas import (
    SystemRateCreate, SystemRateUpdate, SystemRateResponse,
    PartnerRateCreate, PartnerRateUpdate, PartnerRateResponse,
    LedgerEntryCreate, LedgerEntryResponse,
    InvoiceCreate, InvoiceResponse,
    SubscriptionCreate, SubscriptionUpdate, SubscriptionResponse,
    UsageReport, UsageReportLine,
    PartnerEarningsReport, PartnerEarningsLine
)

class BillingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ============= System Rate Methods =============

    async def create_system_rate(self, rate_in: SystemRateCreate) -> SystemRate:
        """Create a new system rate"""
        db_rate = SystemRate(**rate_in.model_dump())
        self.db.add(db_rate)
        await self.db.commit()
        await self.db.refresh(db_rate)
        return db_rate

    async def get_system_rate(self, rate_id: UUID) -> Optional[SystemRate]:
        """Get system rate by ID"""
        result = await self.db.execute(
            select(SystemRate).where(SystemRate.id == rate_id)
        )
        return result.scalar_one_or_none()

    async def get_system_rates(self, active_only: bool = True) -> List[SystemRate]:
        """Get all system rates"""
        query = select(SystemRate)
        if active_only:
            query = query.where(SystemRate.is_active == True)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_system_rate_by_type(self, resource_type: str) -> Optional[SystemRate]:
        """Get active system rate by resource type"""
        result = await self.db.execute(
            select(SystemRate).where(
                and_(
                    SystemRate.resource_type == resource_type,
                    SystemRate.is_active == True
                )
            )
        )
        return result.scalar_one_or_none()

    async def update_system_rate(self, rate_id: UUID, rate_update: SystemRateUpdate) -> Optional[SystemRate]:
        """Update system rate"""
        db_rate = await self.get_system_rate(rate_id)
        if not db_rate:
            return None
        
        update_data = rate_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_rate, key, value)
        
        await self.db.commit()
        await self.db.refresh(db_rate)
        return db_rate

    # ============= Partner Rate Methods =============

    async def create_partner_rate(self, rate_in: PartnerRateCreate) -> PartnerRate:
        """Create a new partner rate with validation"""
        # Get system rate
        system_rate = await self.get_system_rate(rate_in.system_rate_id)
        if not system_rate:
            raise ValueError(f"System rate {rate_in.system_rate_id} not found")
        
        # Validate partner rate >= system rate
        if rate_in.rate < system_rate.rate:
            raise ValueError(
                f"Partner rate ({rate_in.rate}) must be >= system rate ({system_rate.rate})"
            )
        
        db_rate = PartnerRate(**rate_in.model_dump())
        self.db.add(db_rate)
        await self.db.commit()
        await self.db.refresh(db_rate, ["system_rate"])
        return db_rate

    async def get_partner_rate(self, rate_id: UUID) -> Optional[PartnerRate]:
        """Get partner rate by ID"""
        result = await self.db.execute(
            select(PartnerRate)
            .options(selectinload(PartnerRate.system_rate))
            .where(PartnerRate.id == rate_id)
        )
        return result.scalar_one_or_none()

    async def get_partner_rates(self, partner_id: UUID, active_only: bool = True) -> List[PartnerRate]:
        """Get all rates for a partner"""
        query = select(PartnerRate).options(selectinload(PartnerRate.system_rate)).where(
            PartnerRate.partner_id == partner_id
        )
        if active_only:
            query = query.where(PartnerRate.is_active == True)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_partner_rate_for_resource(
        self, partner_id: UUID, resource_type: str
    ) -> Optional[PartnerRate]:
        """Get active partner rate for a specific resource type"""
        result = await self.db.execute(
            select(PartnerRate)
            .join(SystemRate)
            .options(selectinload(PartnerRate.system_rate))
            .where(
                and_(
                    PartnerRate.partner_id == partner_id,
                    PartnerRate.is_active == True,
                    SystemRate.resource_type == resource_type,
                    SystemRate.is_active == True
                )
            )
        )
        return result.scalar_one_or_none()

    async def update_partner_rate(
        self, rate_id: UUID, rate_update: PartnerRateUpdate
    ) -> Optional[PartnerRate]:
        """Update partner rate with validation"""
        db_rate = await self.get_partner_rate(rate_id)
        if not db_rate:
            return None
        
        # If updating rate, validate against system rate
        if rate_update.rate is not None:
            system_rate = await self.get_system_rate(db_rate.system_rate_id)
            if rate_update.rate < system_rate.rate:
                raise ValueError(
                    f"Partner rate ({rate_update.rate}) must be >= system rate ({system_rate.rate})"
                )
        
        update_data = rate_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_rate, key, value)
        
        await self.db.commit()
        await self.db.refresh(db_rate, ["system_rate"])
        return db_rate

    # ============= Ledger Entry Methods =============

    async def create_ledger_entry(self, entry_in: LedgerEntryCreate) -> LedgerEntry:
        """Create an immutable ledger entry"""
        db_entry = LedgerEntry(**entry_in.model_dump())
        self.db.add(db_entry)
        await self.db.commit()
        await self.db.refresh(db_entry)
        return db_entry

    async def calculate_and_create_ledger_entry(
        self,
        tenant_id: UUID,
        partner_id: Optional[UUID],
        execution_id: Optional[UUID],
        resource_type: str,
        quantity: Decimal,
        unit: str,
        entry_metadata: Optional[str] = None
    ) -> LedgerEntry:
        """Calculate costs and create ledger entry automatically"""
        # Get system rate
        system_rate = await self.get_system_rate_by_type(resource_type)
        if not system_rate:
            raise ValueError(f"No active system rate found for resource type: {resource_type}")
        
        # Calculate platform cost
        platform_cost = quantity * system_rate.rate
        
        # Get partner rate if partner exists
        tenant_cost = platform_cost  # Default to platform cost
        if partner_id:
            partner_rate = await self.get_partner_rate_for_resource(partner_id, resource_type)
            if partner_rate:
                tenant_cost = quantity * partner_rate.rate
        
        # Calculate commission
        partner_commission = tenant_cost - platform_cost
        
        # Create ledger entry
        entry_in = LedgerEntryCreate(
            tenant_id=tenant_id,
            partner_id=partner_id,
            execution_id=execution_id,
            resource_type=resource_type,
            quantity=quantity,
            unit=unit,
            platform_cost=platform_cost,
            tenant_cost=tenant_cost,
            partner_commission=partner_commission,
            entry_metadata=entry_metadata
        )

        
        return await self.create_ledger_entry(entry_in)

    async def get_ledger_entries(
        self,
        tenant_id: Optional[UUID] = None,
        partner_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[LedgerEntry]:
        """Query ledger entries with filters"""
        query = select(LedgerEntry)
        
        conditions = []
        if tenant_id:
            conditions.append(LedgerEntry.tenant_id == tenant_id)
        if partner_id:
            conditions.append(LedgerEntry.partner_id == partner_id)
        if start_date:
            conditions.append(LedgerEntry.created_at >= start_date)
        if end_date:
            conditions.append(LedgerEntry.created_at <= end_date)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(LedgerEntry.created_at.desc()).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ============= Reporting Methods =============

    async def get_usage_report(
        self,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime
    ) -> UsageReport:
        """Generate usage report for a tenant"""
        # Query aggregated usage
        result = await self.db.execute(
            select(
                LedgerEntry.resource_type,
                LedgerEntry.unit,
                func.sum(LedgerEntry.quantity).label('total_quantity'),
                func.sum(LedgerEntry.tenant_cost).label('total_cost')
            )
            .where(
                and_(
                    LedgerEntry.tenant_id == tenant_id,
                    LedgerEntry.created_at >= start_date,
                    LedgerEntry.created_at <= end_date
                )
            )
            .group_by(LedgerEntry.resource_type, LedgerEntry.unit)
        )
        
        line_items = []
        total_cost = Decimal('0.0')
        
        for row in result:
            line_items.append(UsageReportLine(
                resource_type=row.resource_type,
                unit=row.unit,
                total_quantity=row.total_quantity or Decimal('0.0'),
                total_cost=row.total_cost or Decimal('0.0')
            ))
            total_cost += (row.total_cost or Decimal('0.0'))
        
        return UsageReport(
            tenant_id=tenant_id,
            period_start=start_date,
            period_end=end_date,
            total_cost=total_cost,
            line_items=line_items
        )

    async def get_partner_earnings(
        self,
        partner_id: UUID,
        start_date: datetime,
        end_date: datetime
    ) -> PartnerEarningsReport:
        """Generate earnings report for a partner"""
        # Query aggregated earnings by tenant
        result = await self.db.execute(
            select(
                LedgerEntry.tenant_id,
                func.sum(LedgerEntry.partner_commission).label('total_commission')
            )
            .where(
                and_(
                    LedgerEntry.partner_id == partner_id,
                    LedgerEntry.created_at >= start_date,
                    LedgerEntry.created_at <= end_date
                )
            )
            .group_by(LedgerEntry.tenant_id)
        )
        
        # Get tenant names
        from src.auth.models import Tenant
        tenant_earnings = []
        total_earnings = Decimal('0.0')
        
        for row in result:
            tenant_result = await self.db.execute(
                select(Tenant).where(Tenant.id == row.tenant_id)
            )
            tenant = tenant_result.scalar_one_or_none()
            
            commission = row.total_commission or Decimal('0.0')
            tenant_earnings.append(PartnerEarningsLine(
                tenant_id=row.tenant_id,
                tenant_name=tenant.name if tenant else "Unknown",
                total_commission=commission
            ))
            total_earnings += commission
        
        return PartnerEarningsReport(
            partner_id=partner_id,
            period_start=start_date,
            period_end=end_date,
            total_earnings=total_earnings,
            tenants=tenant_earnings
        )

    # ============= Invoice Methods =============

    async def generate_invoice(self, invoice_in: InvoiceCreate) -> Invoice:
        """Generate an invoice for a tenant for a specific period"""
        # Get usage report for the period
        usage_report = await self.get_usage_report(
            invoice_in.tenant_id,
            invoice_in.period_start,
            invoice_in.period_end
        )
        
        # Generate invoice number
        invoice_count = await self.db.scalar(select(func.count(Invoice.id)))
        invoice_number = f"INV-{(invoice_count or 0) + 1:06d}"
        
        # Create invoice
        db_invoice = Invoice(
            tenant_id=invoice_in.tenant_id,
            invoice_number=invoice_number,
            total_amount=usage_report.total_cost,
            period_start=invoice_in.period_start,
            period_end=invoice_in.period_end,
            due_date=invoice_in.due_date,
            line_items=str([item.model_dump() for item in usage_report.line_items])
        )
        
        self.db.add(db_invoice)
        await self.db.commit()
        await self.db.refresh(db_invoice)
        return db_invoice

    async def get_invoice(self, invoice_id: UUID) -> Optional[Invoice]:
        """Get invoice by ID"""
        result = await self.db.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        )
        return result.scalar_one_or_none()

    # ============= Subscription Methods =============

    async def create_subscription(self, sub_in: SubscriptionCreate) -> Subscription:
        """Create a new subscription"""
        db_sub = Subscription(**sub_in.model_dump())
        self.db.add(db_sub)
        await self.db.commit()
        await self.db.refresh(db_sub)
        return db_sub

    async def get_subscription(self, tenant_id: UUID) -> Optional[Subscription]:
        """Get active subscription for a tenant"""
        result = await self.db.execute(
            select(Subscription)
            .where(
                and_(
                    Subscription.tenant_id == tenant_id,
                    Subscription.status == "active"
                )
            )
            .order_by(Subscription.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def update_subscription(
        self, subscription_id: UUID, sub_update: SubscriptionUpdate
    ) -> Optional[Subscription]:
        """Update subscription"""
        result = await self.db.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        db_sub = result.scalar_one_or_none()
        
        if not db_sub:
            return None
        
        update_data = sub_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_sub, key, value)
        
        await self.db.commit()
        await self.db.refresh(db_sub)
        return db_sub
