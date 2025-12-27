import asyncio
from src.common.database import AsyncSessionLocal
from src.auth.models import Company, User
from src.ai.models import HierarchicalEntity, ExecutionRun
from src.ai.schemas import EntityType, EntityStatus
from sqlalchemy import select
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
from uuid import UUID
import json

async def verify():
    async with AsyncSessionLocal() as db:
        # 1. Get a Company
        res = await db.execute(select(Company).limit(1))
        company = res.scalar_one_or_none()
        if not company:
            print("No company found")
            return
        
        print(f"Using company: {company.name} ({company.id})")

        # 2. Create a Hierarchical Entity (Action)
        action_name = f"Test Action {UUID(int=0)}"
        new_entity = HierarchicalEntity(
            company_id=company.id,
            type=EntityType.ACTION,
            name=action_name,
            identity={
                "persona": {
                    "system_prompt": "You are a tester.",
                    "examples": [],
                    "behavioral_constraints": []
                }
            },
            planning={
                "static_plan": {
                    "steps": [
                        {
                            "step_id": "86047245-0d3a-4467-85da-0546990499e0",
                            "order": 1,
                            "name": "thoughts",
                            "type": "THOUGHT",
                            "target": {"prompt_template": "Hello {{input}}"},
                            "required": True
                        }
                    ]
                }
            },
            logic_gate={
                "reasoning_config": {
                    "model_provider": "openai",
                    "model_name": "gpt-4o",
                    "temperature": 0.5
                }
            },
            status=EntityStatus.ACTIVE
        )
        db.add(new_entity)
        await db.commit()
        await db.refresh(new_entity)
        print(f"Created Entity: {new_entity.name} ({new_entity.id})")

        # 3. Create an Execution Run
        new_run = ExecutionRun(
            company_id=company.id,
            entity_id=new_entity.id,
            input_data={"input": "World"},
            status="PENDING"
        )
        db.add(new_run)
        await db.commit()
        await db.refresh(new_run)
        print(f"Created Execution Run: {new_run.id}")

        # 4. Verify AIService.get_execution
        from src.ai.service import AIService
        service = AIService(db)
        detail = await service.get_execution(new_run.id, company.id)
        print(f"Retrieved Execution Detail for: {detail.entity.name}")
        print(f"Total Cost: {detail.total_cost_usd}, Total Tokens: {detail.total_tokens}")

        # 5. Clean up (Optional)
        await db.delete(new_run)
        await db.delete(new_entity)
        await db.commit()
        print("Cleanup successful")

if __name__ == "__main__":
    asyncio.run(verify())
