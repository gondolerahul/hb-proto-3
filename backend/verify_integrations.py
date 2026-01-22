import asyncio
from uuid import uuid4
from decimal import Decimal
from sqlalchemy import text
from src.common.database import AsyncSessionLocal
from src.config.models import IntegrationRegistry
from src.ai.usage_service import UsageService
from src.config.service import ConfigService

async def verify():
    async with AsyncSessionLocal() as db:
        config_service = ConfigService(db)
        usage_service = UsageService(db)
        
        # Fetch an existing company_id
        res = await db.execute(text("SELECT id FROM companies LIMIT 1"))
        row = res.fetchone()
        if not row:
            print("No company found in database. Please seed the database first.")
            return
        company_id = row[0]
        print(f"Using company_id: {company_id}")
        
        # Cleanup previously failed runs
        await db.execute(text("DELETE FROM integration_registry WHERE service_sku = 'test-model-in' AND company_id = :cid"), {"cid": company_id})
        await db.commit()
        
        # 1. Create a mock integration with '1M Tokens' unit
        print("Creating mock integration...")
        integration = IntegrationRegistry(
            company_id=company_id,
            provider_name="TestProvider",
            model_name="test-model",
            service_sku="test-model-in",
            service_category="LLM",
            component_type="input_token",
            internal_cost=Decimal("1.000000"),
            cost_unit="1M Tokens",
            status="active"
        )
        db.add(integration)
        await db.commit()
        
        # 2. Verify usage logging with unit conversion
        print("Logging 1,000,000 tokens usage...")
        usage = await usage_service.log_usage(
            company_id=company_id,
            service_sku="test-model-in",
            raw_quantity=1000000.0
        )
        
        print(f"Calculated Cost: {usage.calculated_cost}")
        # Expected cost is (1.0 * 1,000,000) / 1,000,000 = 1.0
        assert usage.calculated_cost == Decimal("1.000000"), f"Expected 1.0, got {usage.calculated_cost}"
        print("Cost calculation verified!")
        
        # 3. Cleanup
        await db.delete(usage)
        await db.delete(integration)
        await db.commit()
        print("Verification successful!")

if __name__ == "__main__":
    asyncio.run(verify())
