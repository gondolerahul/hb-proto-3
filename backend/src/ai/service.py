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
    async def create_entity(self, entity_in: HierarchicalEntityCreate, company_id: UUID, user_id: UUID = None) -> HierarchicalEntity:
        # Prepare data, handling nested Pydantic models and ensuring JSON serializability (e.g. UUID -> str)
        entity_data = entity_in.model_dump(mode='json')
        
        # Flatten identity if provided as nested model to JSONB column
        entity = HierarchicalEntity(**entity_data, company_id=company_id, created_by=user_id)
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

    async def get_entities(self, company_id: UUID, type: EntityType = None, user_role: str = None, is_template: bool = None) -> list[HierarchicalEntity]:
        from sqlalchemy.orm import selectinload
        query = select(HierarchicalEntity)
        
        # Platform administrators can view all entities across all companies
        if user_role != "app_admin":
            query = query.where(HierarchicalEntity.company_id == company_id)
        
        if type:
            query = query.where(HierarchicalEntity.type == type)
        
        # Filter by template flag (None = show all, True = templates only, False = entities only)
        if is_template is not None:
            query = query.where(HierarchicalEntity.is_template == is_template)
        
        query = query.options(selectinload(HierarchicalEntity.execution_runs))
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_entity(self, entity_id: UUID, company_id: UUID, user_role: str = None) -> HierarchicalEntity:
        from sqlalchemy.orm import selectinload
        query = select(HierarchicalEntity).options(selectinload(HierarchicalEntity.execution_runs))
        query = query.where(HierarchicalEntity.id == entity_id)
        
        # Platform administrators can view any entity across all companies
        if user_role != "app_admin":
            query = query.where(HierarchicalEntity.company_id == company_id)
        
        result = await self.db.execute(query)
        entity = result.scalar_one_or_none()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
            
        # Ensure Actions/Skills have at least one step in their plan for the UI to correctly display inputs
        # This is a virtual fallback for UI purposes when no explicit steps are defined
        if entity.type in [EntityType.ACTION, EntityType.SKILL]:
            planning = entity.planning or {}
            static_plan = planning.get("static_plan", {})
            if not static_plan or not static_plan.get("steps"):
                # Construct a virtual plan with a default step
                virtual_planning = planning.copy()
                virtual_planning["static_plan"] = {
                    "enabled": True,
                    "steps": [{
                        "step_id": "default_execute",
                        "name": "Execute",
                        "type": "ACTION",
                        "target": {
                            "prompt_template": entity.description or "Process instruction: {{instruction}}"
                        },
                        "required": True
                    }]
                }
                entity.planning = virtual_planning
                
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
        
        # Delete related execution runs first (they have FK constraint to entity)
        from sqlalchemy import delete
        from src.ai.models import UsageLog
        
        # Get all execution run IDs for this entity (including child runs)
        runs_result = await self.db.execute(
            select(ExecutionRun.id).where(ExecutionRun.entity_id == entity_id)
        )
        parent_run_ids = [r[0] for r in runs_result.fetchall()]
        
        # Get child run IDs
        child_runs_result = await self.db.execute(
            select(ExecutionRun.id).where(ExecutionRun.parent_run_id.in_(parent_run_ids))
        ) if parent_run_ids else None
        child_run_ids = [r[0] for r in child_runs_result.fetchall()] if child_runs_result else []
        
        all_run_ids = parent_run_ids + child_run_ids
        
        if all_run_ids:
            # Delete related logs and approvals first (they have FK to execution_runs)
            await self.db.execute(
                delete(LLMInteractionLog).where(LLMInteractionLog.run_id.in_(all_run_ids))
            )
            await self.db.execute(
                delete(ToolInteractionLog).where(ToolInteractionLog.run_id.in_(all_run_ids))
            )
            await self.db.execute(
                delete(HumanApproval).where(HumanApproval.run_id.in_(all_run_ids))
            )
            await self.db.execute(
                delete(UsageLog).where(UsageLog.run_id.in_(all_run_ids))
            )
            
            # Delete child execution runs first (due to parent_run_id FK)
            if child_run_ids:
                await self.db.execute(
                    delete(ExecutionRun).where(ExecutionRun.id.in_(child_run_ids))
                )
            # Delete parent execution runs
            await self.db.execute(
                delete(ExecutionRun).where(ExecutionRun.id.in_(parent_run_ids))
            )
        
        # Unlink documents from this entity (set entity_id to NULL)
        from sqlalchemy import update
        await self.db.execute(
            update(Document).where(Document.entity_id == entity_id).values(entity_id=None)
        )
        
        await self.db.delete(entity)
        await self.db.commit()

    # Execution
    async def trigger_execution(self, execution_in: ExecutionRunCreate, company_id: UUID, user_id: UUID = None) -> ExecutionRun:
        # Create Execution Record
        execution = ExecutionRun(
            company_id=company_id,
            user_id=user_id,
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
                selectinload(ExecutionRun.llm_logs),
                selectinload(ExecutionRun.tool_logs),
                selectinload(ExecutionRun.human_approvals)
            )
            .where(ExecutionRun.id == execution.id)
        )
        execution = result.scalar_one()

        # Enqueue Job to Arq
        redis = await create_pool(RedisSettings())
        await redis.enqueue_job('run_execution_recursive', str(execution.id))
        await redis.close()

        return execution

    async def get_execution(self, execution_id: UUID, company_id: UUID, user_role: str = None) -> ExecutionRun:
        from sqlalchemy.orm import selectinload, joinedload
        
        # Load detailed trace with logs and approvals (up to 5 levels deep for deep research trees)
        query = select(ExecutionRun).options(
            joinedload(ExecutionRun.entity),
            selectinload(ExecutionRun.llm_logs),
            selectinload(ExecutionRun.tool_logs),
            selectinload(ExecutionRun.human_approvals),
            
            # Level 1 Child Runs
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.entity),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.llm_logs),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.tool_logs),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.human_approvals),
            
            # Level 2 Child Runs (Grandchildren)
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.entity),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.llm_logs),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.tool_logs),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.human_approvals),
            
            # Level 3 Child Runs (Great-grandchildren)
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.entity),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.llm_logs),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.tool_logs),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.human_approvals),

            # Level 4 Child Runs 
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.entity),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.llm_logs),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.tool_logs),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.human_approvals),

            # Level 5 Child Runs (Final fallback)
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.entity),
            selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.child_runs).selectinload(ExecutionRun.llm_logs)
        )
        
        query = query.where(ExecutionRun.id == execution_id)
        
        # Platform administrators can view any execution across all companies
        if user_role != "app_admin":
            query = query.where(ExecutionRun.company_id == company_id)
        
        result = await self.db.execute(query)
        execution = result.scalar_one_or_none()
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        return execution

    async def get_executions(self, company_id: UUID, user_role: str = None) -> list[ExecutionRun]:
        from sqlalchemy.orm import joinedload
        query = select(ExecutionRun).options(joinedload(ExecutionRun.entity))
        
        # Platform administrators can view all executions across all companies
        if user_role != "app_admin":
            query = query.where(ExecutionRun.company_id == company_id)
        
        query = query.where(ExecutionRun.parent_run_id.is_(None))  # Only show root executions in list
        query = query.order_by(ExecutionRun.created_at.desc())
        
        result = await self.db.execute(query)
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
        
        # P0.3 — Notify waiting worker via Redis pub/sub so it can unblock immediately.
        # The execution engine subscribes to "approval:{approval_id}" before gating
        # on the HumanApproval record and awaits this event with a configurable timeout.
        try:
            from arq import create_pool
            from arq.connections import RedisSettings
            _redis = await create_pool(RedisSettings())
            await _redis.publish(
                f"approval:{approval_id}",
                json.dumps({
                    "approval_id": str(approval_id),
                    "status": status,
                    "notes": notes or "",
                    "responded_at": approval.responded_at.isoformat(),
                })
            )
            await _redis.close()
        except Exception:
            # Non-fatal: worker will time out gracefully if Redis is unavailable
            pass
        
        return approval

    async def get_dashboard_stats(self, company_id: UUID, user_role: str = None) -> dict:
        # Platform administrators can view stats across all companies
        if user_role == "app_admin":
            # Active Entities count (all companies)
            entities_count = await self.db.execute(
                select(func.count(HierarchicalEntity.id))
            )
            
            # Executions count (today, all companies)
            today = datetime.now().date()
            executions_count = await self.db.execute(
                select(func.count(ExecutionRun.id))
                .where(func.date(ExecutionRun.created_at) == today)
            )
            
            # Documents count (all companies)
            documents_count = await self.db.execute(select(func.count(Document.id)))
        else:
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
        from sqlalchemy import text
        
        # Get query embedding via Vertex AI
        model_name = "gemini-embedding-004"
        
        from google import genai
        from google.genai import types
        from src.common.genai_factory import build_vertex_genai_client

        try:
            client = await build_vertex_genai_client(
                self.db, company_id,
                http_options={'api_version': 'v1beta'}
            )
        except (RuntimeError, ValueError) as e:
            raise HTTPException(
                status_code=500,
                detail=f"Vertex AI not configured: {e}. Please add a Google Vertex AI integration."
            )

        try:
            response = client.models.embed_content(
                model=model_name,
                contents=query,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
            )
            query_embedding = response.embeddings[0].values
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Vertex AI Embedding API Error: {str(e)}")
        
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

    # ── Template Management ────────────────────────────────────────────────

    async def clone_template(self, template_id: UUID, company_id: UUID, user_id: UUID) -> HierarchicalEntity:
        """
        Deep-clone a template entity (and all its children) into executable
        entities owned by the requesting company/user.
        """
        from sqlalchemy.orm import selectinload

        # 1. Load the template
        result = await self.db.execute(
            select(HierarchicalEntity)
            .options(selectinload(HierarchicalEntity.execution_runs))
            .where(
                HierarchicalEntity.id == template_id,
                HierarchicalEntity.is_template == True,
            )
        )
        template = result.scalar_one_or_none()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # 2. Collect all child entities that belong to this template hierarchy
        async def _collect_children(parent_id: UUID) -> list[HierarchicalEntity]:
            res = await self.db.execute(
                select(HierarchicalEntity).where(
                    HierarchicalEntity.parent_id == parent_id,
                    HierarchicalEntity.is_template == True,
                )
            )
            children = list(res.scalars().all())
            grandchildren = []
            for child in children:
                grandchildren.extend(await _collect_children(child.id))
            return children + grandchildren

        all_children = await _collect_children(template.id)

        # 3. Clone root template
        old_to_new_id: dict[UUID, UUID] = {}

        def _clone_fields(src: HierarchicalEntity) -> dict:
            """Extract clonable fields from a template entity."""
            return {
                "name": src.name,
                "display_name": src.display_name,
                "description": src.description,
                "goal": src.goal,
                "type": src.type,
                "version": src.version,
                "status": src.status,
                "tags": src.tags,
                "identity": src.identity,
                "hierarchy": src.hierarchy,
                "logic_gate": src.logic_gate,
                "planning": src.planning,
                "capabilities": src.capabilities,
                "governance": src.governance,
                "io_contract": src.io_contract,
                "observability": src.observability,
                "metadata_extensions": src.metadata_extensions,
            }

        root_clone = HierarchicalEntity(
            **_clone_fields(template),
            company_id=company_id,
            created_by=user_id,
            is_template=False,
            template_source_id=template.id,
            parent_id=None,
        )
        self.db.add(root_clone)
        await self.db.flush()  # get root_clone.id assigned
        old_to_new_id[template.id] = root_clone.id

        # 4. Clone children in topological order (parent before child)
        for child in all_children:
            new_parent_id = old_to_new_id.get(child.parent_id)
            clone = HierarchicalEntity(
                **_clone_fields(child),
                company_id=company_id,
                created_by=user_id,
                is_template=False,
                template_source_id=child.id,
                parent_id=new_parent_id,
            )
            self.db.add(clone)
            await self.db.flush()
            old_to_new_id[child.id] = clone.id

        await self.db.commit()

        # 5. Reload with relationships
        result = await self.db.execute(
            select(HierarchicalEntity)
            .options(selectinload(HierarchicalEntity.execution_runs))
            .where(HierarchicalEntity.id == root_clone.id)
        )
        return result.scalar_one()
