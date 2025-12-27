import asyncio
import uuid
from src.common.database import AsyncSessionLocal
from src.ai.models import EntityType, HierarchicalEntity
from src.ai.schemas import HierarchicalEntityCreate, ExecutionRunCreate
from src.ai.service import AIService
from src.auth.models import Company, User
from sqlalchemy import select
import src.config.models # Needed for IntegrationRegistry relationship


async def seed():
    async with AsyncSessionLocal() as session:
        # 1. Find Company
        result = await session.execute(select(Company))
        company = result.scalars().first()
        if not company:
            print("No company found. Please run seed_db.py first.")
            return
        company_id = company.id
        print(f"Using Company: {company.name} ({company_id})")

        service = AIService(session)

        # 2. Create Action
        action_in = HierarchicalEntityCreate(
            name="Generate Joke Action",
            type=EntityType.ACTION,
            llm_config={
                "provider": "openai",
                "model": "gpt-3.5-turbo"
            },
            static_plan={
                "prompt_template": "Tell me a joke about {{topic}}."
            }
        )
        action = await service.create_entity(action_in, company_id)
        print(f"Created Action: {action.name} ({action.id})")

        # 3. Create Skill
        skill_in = HierarchicalEntityCreate(
            name="Joke Skill",
            type=EntityType.SKILL,
            static_plan={
                "steps": [
                    {
                        "id": "step_1",
                        "entity_id": str(action.id),
                        "entity_name": action.name
                    }
                ]
            }
        )
        skill = await service.create_entity(skill_in, company_id)
        print(f"Created Skill: {skill.name} ({skill.id})")

        # 4. Create Agent
        agent_in = HierarchicalEntityCreate(
            name="Comedian Agent",
            type=EntityType.AGENT,
            static_plan={
                "steps": [
                    {
                        "id": "step_1",
                        "entity_id": str(skill.id),
                        "entity_name": skill.name
                    }
                ]
            }
        )
        agent = await service.create_entity(agent_in, company_id)
        print(f"Created Agent: {agent.name} ({agent.id})")

        # 5. Trigger Execution
        print("Triggering execution on Agent...")
        execution_in = ExecutionRunCreate(
            entity_id=agent.id,
            input_data={"topic": "AI Engineers"}
        )
        
        execution = await service.trigger_execution(execution_in, company_id)
        print(f"Execution Triggered! ID: {execution.id}")
        
        # Note: Worker needs to be running to process this.
        # We can't easily wait for it here without polling or connecting to redis.
        print("Check database or logs for progress.")

if __name__ == "__main__":
    asyncio.run(seed())
