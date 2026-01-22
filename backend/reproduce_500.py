import asyncio
from uuid import uuid4
from sqlalchemy import text
from src.common.database import AsyncSessionLocal
from src.ai.service import AIService
from src.ai.models import HierarchicalEntity

async def reproduce():
    async with AsyncSessionLocal() as db:
        # Get a company_id
        res = await db.execute(text("SELECT id FROM companies LIMIT 1"))
        company_id = res.scalar()
        if not company_id:
            print("No company found.")
            return

        print(f"Testing get_entities for company: {company_id}")
        service = AIService(db)
        try:
            entities = await service.get_entities(company_id=company_id)
            print(f"Success! Found {len(entities)} entities.")
            
            from src.ai.schemas import HierarchicalEntityResponse
            print("Attempting Pydantic validation...")
            for e in entities:
                try:
                    HierarchicalEntityResponse.model_validate(e)
                except Exception as ve:
                    print(f"Validation failed for entity {e.id}: {ve}")
                    # Print raw data to see what's wrong
                    print(f"Identity raw: {e.identity}")
                    
            print("Validation check complete.")
            
        except Exception as e:
            print(f"Error fetching entities: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(reproduce())
