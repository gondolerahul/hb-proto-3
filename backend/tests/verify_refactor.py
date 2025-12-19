import asyncio
import os
import sys
from uuid import uuid4
from decimal import Decimal

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.common.security import encrypt_api_key, decrypt_api_key
from src.common.database import AsyncSessionLocal
from src.config.models import IntegrationRegistry
from src.ai.models import UsageLog, Execution
from src.ai.usage_service import UsageService
from src.auth.models import Company
from sqlalchemy import select

async def verify_encryption():
    print("--- Verifying Encryption ---")
    test_key = "sk-test-1234567890"
    encrypted = encrypt_api_key(test_key)
    decrypted = decrypt_api_key(encrypted)
    
    print(f"Original: {test_key}")
    print(f"Encrypted: {encrypted[:20]}...")
    print(f"Decrypted: {decrypted}")
    
    assert test_key == decrypted
    print("Encryption Verified!")

async def verify_usage_logging():
    print("\n--- Verifying Usage Logging ---")
    async with AsyncSessionLocal() as db:
        # 1. Ensure a company exists
        result = await db.execute(select(Company).limit(1))
        company = result.scalar_one_or_none()
        if not company:
            # Create a dummy company for testing
            company = Company(id=uuid4(), name="Test Company", type="TENANT")
            db.add(company)
            await db.commit()
            await db.refresh(company)
        
        print(f"Using Company: {company.name} ({company.id})")

        # 2. Create an Integration Registry entry (SKU)
        sku_name = f"test-sku-{uuid4().hex[:8]}"
        sku_in = IntegrationRegistry(
            company_id=company.id,
            provider_name="OpenAI",
            model_name="gpt-4o",
            service_sku=sku_name,
            component_type="input_token",
            encrypted_api_key=encrypt_api_key("fake-key"),
            internal_cost=Decimal("0.000005"),
            cost_unit="Token",
            status="active"
        )
        db.add(sku_in)
        await db.commit()
        await db.refresh(sku_in)
        print(f"Created SKU: {sku_in.service_sku} with cost {sku_in.internal_cost}")

        # 3. Log usage
        usage_service = UsageService(db)
        log = await usage_service.log_usage(
            company_id=company.id,
            service_sku=sku_name,
            raw_quantity=1000.0,
            metadata={"test": "true"}
        )
        
        print(f"Logged Usage: {log.raw_quantity} units, Calculated Cost: {log.calculated_cost}")
        
        assert log.calculated_cost == Decimal("0.005000")
        print("Usage Logging Verified!")
        
        # Cleanup (optional, but good for repeatability)
        await db.delete(log)
        await db.delete(sku_in)
        await db.commit()

async def main():
    try:
        await verify_encryption()
        await verify_usage_logging()
        print("\nALL VERIFICATIONS PASSED!")
    except Exception as e:
        print(f"\nVERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
