import asyncio
from src.ai.service import AIService
from src.common.database import AsyncSessionLocal
from src.ai.models import EntityType, HierarchicalEntity
from src.auth.models import Company
from src.ai.schemas import ExecutionRunCreate
from sqlalchemy import select
import src.config.models
import src.auth.models

async def trigger():
    async with AsyncSessionLocal() as session:
        # Get Company
        result = await session.execute(select(Company))
        company = result.scalars().first()
        if not company:
            print("No company")
            return

        # Get Agent
        result = await session.execute(
            select(HierarchicalEntity)
            .where(HierarchicalEntity.name == "Comedian Agent", HierarchicalEntity.company_id == company.id)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            print("Agent not found")
            return

        print(f"Triggering Agent: {agent.name} ({agent.id})")
        
        service = AIService(session)
        execution_in = ExecutionRunCreate(
            entity_id=agent.id,
            input_data={"topic": "Recursive AI"}
        )
        execution = await service.trigger_execution(execution_in, company.id)
        print(f"New Execution ID: {execution.id}")

if __name__ == "__main__":
    asyncio.run(trigger())
