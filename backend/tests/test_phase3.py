import pytest
import asyncio
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.common.database import Base, get_db
from src.auth.models import User, Tenant
from src.config.service import ConfigService
from src.config.schemas import AIModelCreate
from src.ai.service import AIService
from src.ai.schemas import AgentCreate, ModelConfig, ExecutionCreate
from src.ai.worker import run_execution

# Use an in-memory SQLite database for testing or the actual Postgres if available
# For this environment, we'll use the actual Postgres connection string from .env if possible,
# or fallback to sqlite. But since we have asyncpg, we need postgres.
# We will assume the test environment has access to the DB.

@pytest.mark.asyncio
async def test_phase3_flow():
    # Setup DB
    from src.common.database import engine, AsyncSessionLocal
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # 1. Setup Tenant and User
        tenant_id = uuid4()
        tenant = Tenant(id=tenant_id, name="Test Tenant")
        db.add(tenant)
        
        user = User(
            email=f"test_phase3_{uuid4()}@example.com",
            full_name="Test User",
            hashed_password="hashed_secret",
            tenant_id=tenant_id,
            role="tenant_admin"
        )
        db.add(user)
        await db.commit()

        # 2. System Config: Create AI Model
        config_service = ConfigService(db)
        model_in = AIModelCreate(
            model_key="gpt-4-test",
            provider="openai",
            model_type="text"
        )
        await config_service.create_ai_model(model_in)

        # 3. AI Builder: Create Agent
        ai_service = AIService(db)
        agent_in = AgentCreate(
            name="Test Agent",
            role="You are a helpful assistant.",
            llm_config=ModelConfig(provider="openai", model="gpt-4-test")
        )
        agent = await ai_service.create_agent(agent_in, tenant_id)
        assert agent.id is not None
        assert agent.name == "Test Agent"

        # 4. Execution: Trigger Execution
        execution_in = ExecutionCreate(
            agent_id=agent.id,
            input_data={"prompt": "Hello world"}
        )
        # We need to mock redis enqueueing or it will fail if redis is not running/configured
        # For this test, we can just let it try (and fail silently if we catch it) or mock it.
        # But wait, the service tries to connect to Redis.
        # Let's mock `create_pool` in `src.ai.service`.
        
        import unittest.mock
        with unittest.mock.patch('src.ai.service.create_pool') as mock_redis:
             mock_pool = unittest.mock.AsyncMock()
             mock_redis.return_value = mock_pool
             
             execution = await ai_service.trigger_execution(execution_in, tenant_id)
             assert execution.id is not None
             assert execution.status == "pending"

        # 5. Worker: Process Execution manually
        # We need to pass the execution ID as string
        await run_execution(None, str(execution.id))

        # 6. Verify Result
        await db.refresh(execution)
        assert execution.status == "completed"
        assert execution.result_data is not None
        assert "Processed by agent Test Agent" in execution.result_data["output"]

    print("Phase 3 Test Passed Successfully!")
