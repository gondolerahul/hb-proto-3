from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from fastapi import HTTPException
from uuid import UUID, uuid4
from arq import create_pool
from arq.connections import RedisSettings
from src.ai.models import (
    HierarchicalEntity, ExecutionRun, LLMInteractionLog, 
    ToolInteractionLog, HumanApproval, Document, EntityType
)
from src.ai.schemas import (
    HierarchicalEntityCreate, HierarchicalEntityUpdate, ExecutionRunCreate
)
from datetime import datetime
import json

class AIService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # Entity CRUD
    async def create_entity(self, entity_in: HierarchicalEntityCreate, company_id: UUID) -> HierarchicalEntity:
        # Prepare data, handling nested Pydantic models
        entity_data = entity_in.model_dump()
        
        # Flatten identity if provided as nested model to JSONB column
        entity = HierarchicalEntity(**entity_data, company_id=company_id)
        self.db.add(entity)
        await self.db.commit()
        
        # Reload with relationships for schema
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(HierarchicalEntity)
            .options(
                selectinload(HierarchicalEntity.execution_runs)
            )
            .where(HierarchicalEntity.id == entity.id)
        )
        return result.scalar_one()

    async def get_entities(self, company_id: UUID, type: EntityType = None) -> list[HierarchicalEntity]:
        from sqlalchemy.orm import selectinload
        query = select(HierarchicalEntity).where(HierarchicalEntity.company_id == company_id)
        if type:
            query = query.where(HierarchicalEntity.type == type)
        
        query = query.options(selectinload(HierarchicalEntity.execution_runs))
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_entity(self, entity_id: UUID, company_id: UUID) -> HierarchicalEntity:
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(HierarchicalEntity)
            .options(selectinload(HierarchicalEntity.execution_runs))
            .where(HierarchicalEntity.id == entity_id, HierarchicalEntity.company_id == company_id)
        )
        entity = result.scalar_one_or_none()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        return entity

    async def update_entity(self, entity_id: UUID, entity_in: HierarchicalEntityUpdate, company_id: UUID) -> HierarchicalEntity:
        entity = await self.get_entity(entity_id, company_id)
        
        update_data = entity_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(entity, field, value)
            
        self.db.add(entity)
        await self.db.commit()
        await self.db.refresh(entity)
        return entity

    async def delete_entity(self, entity_id: UUID, company_id: UUID):
        entity = await self.get_entity(entity_id, company_id)
        await self.db.delete(entity)
        await self.db.commit()

    # Execution
    async def trigger_execution(self, execution_in: ExecutionRunCreate, company_id: UUID) -> ExecutionRun:
        # Create Execution Record
        execution = ExecutionRun(
            company_id=company_id,
            entity_id=execution_in.entity_id,
            input_data=execution_in.input_data,
            status="PENDING",
            trace_id=uuid4() # Initialize root trace
        )
        self.db.add(execution)
        await self.db.commit()
        
        # Load relationships for response schema
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(ExecutionRun)
            .options(
                selectinload(ExecutionRun.entity),
                selectinload(ExecutionRun.child_runs),
                selectinload(ExecutionRun.llm_logs)
            )
            .where(ExecutionRun.id == execution.id)
        )
        execution = result.scalar_one()

        # Enqueue Job to Arq
        redis = await create_pool(RedisSettings())
        await redis.enqueue_job('run_execution_recursive', str(execution.id))
        await redis.close()

        return execution

    async def get_execution(self, execution_id: UUID, company_id: UUID) -> ExecutionRun:
        from sqlalchemy.orm import selectinload, joinedload
        
        # Load detailed trace with logs and approvals
        result = await self.db.execute(
            select(ExecutionRun)
            .options(
                joinedload(ExecutionRun.entity),
                selectinload(ExecutionRun.llm_logs),
                selectinload(ExecutionRun.tool_logs),
                selectinload(ExecutionRun.human_approvals),
                selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.entity),
                selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.llm_logs),
                selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.tool_logs),
                selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.human_approvals),
                selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.entity),
                selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.llm_logs)
            )
            .where(ExecutionRun.id == execution_id, ExecutionRun.company_id == company_id)
        )
        execution = result.scalar_one_or_none()
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        return execution

    async def get_executions(self, company_id: UUID) -> list[ExecutionRun]:
        from sqlalchemy.orm import joinedload
        result = await self.db.execute(
            select(ExecutionRun)
            .options(
                joinedload(ExecutionRun.entity)
            )
            .where(ExecutionRun.company_id == company_id)
            .where(ExecutionRun.parent_run_id.is_(None)) # Only show root executions in list
            .order_by(ExecutionRun.created_at.desc())
        )
        return result.scalars().all()

    # HITL Management
    async def get_pending_approvals(self, company_id: UUID) -> list[HumanApproval]:
        result = await self.db.execute(
            select(HumanApproval)
            .join(ExecutionRun)
            .where(ExecutionRun.company_id == company_id, HumanApproval.status == "PENDING")
            .order_by(HumanApproval.requested_at.desc())
        )
        return result.scalars().all()

    async def respond_to_approval(self, approval_id: UUID, status: str, user_id: UUID, notes: str = None) -> HumanApproval:
        result = await self.db.execute(select(HumanApproval).where(HumanApproval.id == approval_id))
        approval = result.scalar_one_or_none()
        if not approval:
            raise HTTPException(status_code=404, detail="Approval request not found")
        
        approval.status = status
        approval.responded_by = user_id
        approval.responded_at = datetime.utcnow()
        approval.reviewer_notes = notes
        
        await self.db.commit()
        await self.db.refresh(approval)
        
        # TODO: Notify worker that approval is received (e.g. via Redis/Event)
        
        return approval

    async def get_dashboard_stats(self, company_id: UUID) -> dict:
        # Active Entities count
        entities_count = await self.db.execute(
            select(func.count(HierarchicalEntity.id))
            .where(HierarchicalEntity.company_id == company_id)
        )
        
        # Executions count (today)
        today = datetime.now().date()
        executions_count = await self.db.execute(
            select(func.count(ExecutionRun.id))
            .where(ExecutionRun.company_id == company_id)
            .where(func.date(ExecutionRun.created_at) == today)
        )
        
        # Documents count
        documents_count = await self.db.execute(select(func.count(Document.id)).where(Document.company_id == company_id))
        
        return {
            "entities_total": entities_count.scalar() or 0,
            "executions_today": executions_count.scalar() or 0,
            "documents_total": documents_count.scalar() or 0
        }

    # Document & RAG Methods
    async def upload_document(self, file_content: bytes, filename: str, file_type: str, company_id: UUID, entity_id: UUID = None):
        # Create document record
        document = Document(
            company_id=company_id,
            entity_id=entity_id,
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
    
    async def search_documents(self, query: str, company_id: UUID, entity_id: UUID = None, top_k: int = 5):
        from src.ai.models import DocumentChunk
        from src.config.service import ConfigService
        import httpx
        from sqlalchemy import text
        
        # Get query embedding
        config_service = ConfigService(self.db)
        gemini_api_key = await config_service.get_api_key_by_sku(company_id, "gemini-embedding-004")
        
        if not gemini_api_key:
            # Fallback to general gemini SKU if specific embedding SKU is not found
            gemini_api_key = await config_service.get_api_key_by_sku(company_id, "gemini-api-key")
            
        if not gemini_api_key:
            raise HTTPException(status_code=500, detail="Gemini API Key not found in Integrations for this company")
        
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
            WHERE d.company_id = :company_id
            AND (:entity_id::uuid IS NULL OR d.entity_id = :entity_id)
            ORDER BY dc.embedding <=> :query_embedding::vector
            LIMIT :top_k
        """)
        
        result = await self.db.execute(
            sql,
            {
                "query_embedding": str(query_embedding),
                "company_id": str(company_id),
                "entity_id": str(entity_id) if entity_id else None,
                "top_k": top_k
            }
        )
        
        return result.fetchall()
    
    async def get_documents(self, company_id: UUID, entity_id: UUID = None):
        query = select(Document).where(Document.company_id == company_id)
        if entity_id:
            query = query.where(Document.entity_id == entity_id)
        
        result = await self.db.execute(query)
        return result.scalars().all()
