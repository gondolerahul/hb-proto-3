from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.ai.models import UsageLog
from src.config.models import IntegrationRegistry

class UsageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_usage(
        self,
        company_id: UUID,
        service_sku: str,
        raw_quantity: float,
        execution_id: Optional[UUID] = None,
        metadata: Optional[dict] = None
    ) -> UsageLog:
        """
        Logs usage for a specific SKU and company.
        Calculates cost based on the internal_cost in IntegrationRegistry.
        """
        # Fetch the SKU configuration
        result = await self.db.execute(
            select(IntegrationRegistry).where(
                IntegrationRegistry.company_id == company_id,
                IntegrationRegistry.service_sku == service_sku,
                IntegrationRegistry.status == "active"
            )
        )
        registry_entry = result.scalar_one_or_none()
        
        if not registry_entry:
            # Fallback to a global/default SKU if needed, or raise error
            # For now, we assume company-specific SKUs must exist
            print(f"WARNING: No active registry entry found for SKU {service_sku} and company {company_id}")
            return None

        # Calculate cost
        # registry_entry.internal_cost is Decimal(18,6)
        # raw_quantity is float (e.g. number of tokens)
        
        # Support unit-based costing (e.g., 1M Tokens)
        divisor = Decimal("1.0")
        if registry_entry.cost_unit:
            if "1M Tokens" in registry_entry.cost_unit:
                divisor = Decimal("1000000.0")
            elif "1K Tokens" in registry_entry.cost_unit:
                divisor = Decimal("1000.0")
            elif "1000 Characters" in registry_entry.cost_unit:
                divisor = Decimal("1000.0")
        
        calculated_cost = (registry_entry.internal_cost * Decimal(str(raw_quantity))) / divisor

        usage_log = UsageLog(
            company_id=company_id,
            run_id=execution_id,
            sku_id=registry_entry.id,
            raw_quantity=Decimal(str(raw_quantity)),
            calculated_cost=calculated_cost,
            log_metadata=metadata
        )
        
        self.db.add(usage_log)
        await self.db.commit()
        await self.db.refresh(usage_log)
        return usage_log
