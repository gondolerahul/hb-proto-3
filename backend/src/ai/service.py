from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from uuid import UUID
from arq import create_pool
from arq.connections import RedisSettings
from src.ai.models import Agent, Workflow, Execution
from src.ai.schemas import AgentCreate, AgentUpdate, WorkflowCreate, WorkflowUpdate, ExecutionCreate
from datetime import datetime

class AIService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # Agent CRUD
    async def create_agent(self, agent_in: AgentCreate, tenant_id: UUID) -> Agent:
        agent = Agent(**agent_in.model_dump(), tenant_id=tenant_id)
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def get_agents(self, tenant_id: UUID) -> list[Agent]:
        result = await self.db.execute(select(Agent).where(Agent.tenant_id == tenant_id))
        return result.scalars().all()

    async def get_agent(self, agent_id: UUID, tenant_id: UUID) -> Agent:
        result = await self.db.execute(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == tenant_id))
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent

    async def update_agent(self, agent_id: UUID, agent_in: AgentUpdate, tenant_id: UUID) -> Agent:
        agent = await self.get_agent(agent_id, tenant_id)
        
        update_data = agent_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(agent, field, value)
            
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    # Workflow CRUD
    async def create_workflow(self, workflow_in: WorkflowCreate, tenant_id: UUID) -> Workflow:
        workflow = Workflow(**workflow_in.model_dump(), tenant_id=tenant_id)
        self.db.add(workflow)
        await self.db.commit()
        await self.db.refresh(workflow)
        return workflow

    async def get_workflows(self, tenant_id: UUID) -> list[Workflow]:
        result = await self.db.execute(select(Workflow).where(Workflow.tenant_id == tenant_id))
        return result.scalars().all()

    async def get_workflow(self, workflow_id: UUID, tenant_id: UUID) -> Workflow:
        result = await self.db.execute(select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id))
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return workflow

    async def update_workflow(self, workflow_id: UUID, workflow_in: WorkflowUpdate, tenant_id: UUID) -> Workflow:
        from sqlalchemy.orm.attributes import flag_modified
        
        workflow = await self.get_workflow(workflow_id, tenant_id)
        
        # Use mode='json' to ensure nested Pydantic models (like WorkflowDAG) and special types (UUID, datetime)
        # are converted to JSON-native types (dicts, strings) before being passed to SQLAlchemy's JSON column.
        update_data = workflow_in.model_dump(exclude_unset=True, mode='json')
        
        for field, value in update_data.items():
            setattr(workflow, field, value)
            if field == 'dag_structure':
                flag_modified(workflow, "dag_structure")
        
        self.db.add(workflow)
        await self.db.commit()
        await self.db.refresh(workflow)
        
        return workflow

    # Execution
    async def trigger_execution(self, execution_in: ExecutionCreate, tenant_id: UUID) -> Execution:
        # Create Execution Record
        execution = Execution(
            tenant_id=tenant_id,
            agent_id=execution_in.agent_id,
            workflow_id=execution_in.workflow_id,
            input_data=execution_in.input_data,
            status="pending"
        )
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(execution)

        # Enqueue Job to Arq
        redis = await create_pool(RedisSettings())
        await redis.enqueue_job('run_execution', str(execution.id))
        await redis.close()

        return execution

    async def get_execution(self, execution_id: UUID, tenant_id: UUID) -> Execution:
        result = await self.db.execute(select(Execution).where(Execution.id == execution_id, Execution.tenant_id == tenant_id))
        execution = result.scalar_one_or_none()
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        return execution

    async def get_executions(self, tenant_id: UUID) -> list[Execution]:
        result = await self.db.execute(
            select(Execution)
            .where(Execution.tenant_id == tenant_id)
            .order_by(Execution.created_at.desc())
        )
        return result.scalars().all()

    async def get_dashboard_stats(self, tenant_id: UUID) -> dict:
        from src.ai.models import Document
        from sqlalchemy import func
        
        # Agents count
        agents_count = await self.db.execute(select(func.count(Agent.id)).where(Agent.tenant_id == tenant_id))
        
        # Workflows count
        workflows_count = await self.db.execute(select(func.count(Workflow.id)).where(Workflow.tenant_id == tenant_id))
        
        # Executions count (today)
        today = datetime.now().date()
        executions_count = await self.db.execute(
            select(func.count(Execution.id))
            .where(Execution.tenant_id == tenant_id)
            .where(func.date(Execution.created_at) == today)
        )
        
        # Documents count
        documents_count = await self.db.execute(select(func.count(Document.id)).where(Document.tenant_id == tenant_id))
        
        return {
            "agents_active": agents_count.scalar() or 0,
            "workflows_active": workflows_count.scalar() or 0,
            "executions_today": executions_count.scalar() or 0,
            "documents_total": documents_count.scalar() or 0
        }

    # Document & RAG Methods
    async def upload_document(self, file_content: bytes, filename: str, file_type: str, tenant_id: UUID, agent_id: UUID = None):
        from src.ai.models import Document
        from arq import create_pool
        from arq.connections import RedisSettings
        
        # Create document record
        document = Document(
            tenant_id=tenant_id,
            agent_id=agent_id,
            filename=filename,
            file_type=file_type,
            file_size=str(len(file_content)),
            upload_status="processing"
        )
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        
        # Enqueue Job to Arq
        redis = await create_pool(RedisSettings())
        await redis.enqueue_job(
            'process_document', 
            str(document.id),
            file_content,
            file_type,
            filename
        )
        await redis.close()
        
        return document
    
    async def search_documents(self, query: str, tenant_id: UUID, agent_id: UUID = None, top_k: int = 5):
        from src.ai.models import Document, DocumentChunk
        import httpx
        import os
        from sqlalchemy import text
        
        # Get query embedding
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY not found")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={gemini_api_key}"
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "model": "models/text-embedding-004",
                    "content": {
                        "parts": [{"text": query}]
                    }
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Gemini Embedding API Error: {response.text}")
            
            data = response.json()
            query_embedding = data["embedding"]["values"]
        
        # Search using cosine similarity
        sql = text("""
            SELECT 
                dc.id as chunk_id,
                dc.document_id,
                d.filename,
                dc.content,
                1 - (dc.embedding <=> :query_embedding::vector) as similarity
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE d.tenant_id = :tenant_id
            AND (:agent_id::uuid IS NULL OR d.agent_id = :agent_id)
            ORDER BY dc.embedding <=> :query_embedding::vector
            LIMIT :top_k
        """)
        
        result = await self.db.execute(
            sql,
            {
                "query_embedding": str(query_embedding),
                "tenant_id": str(tenant_id),
                "agent_id": str(agent_id) if agent_id else None,
                "top_k": top_k
            }
        )
        
        return result.fetchall()
    
    async def get_documents(self, tenant_id: UUID, agent_id: UUID = None):
        from src.ai.models import Document
        
        query = select(Document).where(Document.tenant_id == tenant_id)
        if agent_id:
            query = query.where(Document.agent_id == agent_id)
        
        result = await self.db.execute(query)
        return result.scalars().all()
