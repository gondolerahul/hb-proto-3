from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, or_
from fastapi import HTTPException
from uuid import UUID, uuid4
from arq import create_pool
import re
import logging
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

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # Entity CRUD
    async def create_entity(self, entity_in: HierarchicalEntityCreate, company_id: UUID, user_id: UUID = None) -> HierarchicalEntity:
        # Prepare data, handling nested Pydantic models and ensuring JSON serializability (e.g. UUID -> str)
        entity_data = entity_in.model_dump(mode='json')
        
        # Templates are public — no company association
        effective_company_id = None if entity_data.get("is_template") else company_id
        
        # Flatten identity if provided as nested model to JSONB column
        entity = HierarchicalEntity(**entity_data, company_id=effective_company_id, created_by=user_id)
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

    async def get_entities(self, company_id: UUID, type: EntityType = None, user_role: str = None, is_template: bool = None, voice_enabled: bool = None, status_filter: str = None) -> list[HierarchicalEntity]:
        from sqlalchemy.orm import selectinload
        query = select(HierarchicalEntity)
        
        # Templates are public (company_id=NULL) — visible to everyone
        if is_template is True:
            query = query.where(HierarchicalEntity.is_template == True)
        else:
            # For regular entities, scope by company (app_admin sees all)
            if user_role != "app_admin":
                query = query.where(HierarchicalEntity.company_id == company_id)
            # Filter by template flag (None = show all, False = entities only)
            if is_template is not None:
                query = query.where(HierarchicalEntity.is_template == is_template)
        
        if type:
            query = query.where(HierarchicalEntity.type == type)
        
        if status_filter:
            query = query.where(HierarchicalEntity.status == status_filter)
        
        query = query.options(selectinload(HierarchicalEntity.execution_runs))
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_entity(self, entity_id: UUID, company_id: UUID, user_role: str = None) -> HierarchicalEntity:
        from sqlalchemy.orm import selectinload
        query = select(HierarchicalEntity).options(selectinload(HierarchicalEntity.execution_runs))
        query = query.where(HierarchicalEntity.id == entity_id)
        
        # Platform administrators can view any entity; templates are public
        if user_role != "app_admin":
            from sqlalchemy import or_
            query = query.where(
                or_(
                    HierarchicalEntity.company_id == company_id,
                    HierarchicalEntity.is_template == True,
                )
            )
        
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
        
        update_data = entity_in.model_dump(mode='json', exclude_unset=True)
        for field, value in update_data.items():
            setattr(entity, field, value)
            
        self.db.add(entity)
        await self.db.commit()
        await self.db.refresh(entity)
        return entity

    async def delete_entity(self, entity_id: UUID, company_id: UUID):
        entity = await self.get_entity(entity_id, company_id)
        
        from sqlalchemy import delete, update
        from src.ai.models import UsageLog, EpisodicMemory
        
        # ── Collect the full entity tree (this entity + all descendants) ──
        # A PROCESS entity may have child entities (agents, skills) that
        # must also be deleted to avoid orphans.
        async def _collect_entity_tree(eid: UUID, visited: set[UUID]) -> list[UUID]:
            if eid in visited:
                return []
            visited.add(eid)
            child_result = await self.db.execute(
                select(HierarchicalEntity.id).where(
                    HierarchicalEntity.parent_id == eid
                )
            )
            child_ids = [r[0] for r in child_result.fetchall()]
            descendants = []
            for cid in child_ids:
                descendants.extend(await _collect_entity_tree(cid, visited))
            return [eid] + descendants

        all_entity_ids = await _collect_entity_tree(entity_id, set())
        logger.info(f"delete_entity: deleting {len(all_entity_ids)} entities (root + descendants)")

        # ── Collect ALL execution run IDs across all entities in the tree ──
        runs_result = await self.db.execute(
            select(ExecutionRun.id).where(ExecutionRun.entity_id.in_(all_entity_ids))
        )
        direct_run_ids = [r[0] for r in runs_result.fetchall()]
        
        # Also collect child runs (runs spawned by parent runs)
        all_run_ids = list(direct_run_ids)
        if direct_run_ids:
            child_runs_result = await self.db.execute(
                select(ExecutionRun.id).where(ExecutionRun.parent_run_id.in_(direct_run_ids))
            )
            child_run_ids = [r[0] for r in child_runs_result.fetchall()]
            all_run_ids.extend(child_run_ids)
        
        if all_run_ids:
            # ── Delete records that reference execution_runs ──
            
            # 1. LLM interaction logs
            await self.db.execute(
                delete(LLMInteractionLog).where(LLMInteractionLog.run_id.in_(all_run_ids))
            )
            # 2. Tool interaction logs
            await self.db.execute(
                delete(ToolInteractionLog).where(ToolInteractionLog.run_id.in_(all_run_ids))
            )
            # 3. Human approvals
            await self.db.execute(
                delete(HumanApproval).where(HumanApproval.run_id.in_(all_run_ids))
            )
            # 4. Usage logs
            await self.db.execute(
                delete(UsageLog).where(UsageLog.run_id.in_(all_run_ids))
            )
            # 5. Episodic memories (reference both entity_id and run_id)
            await self.db.execute(
                delete(EpisodicMemory).where(EpisodicMemory.run_id.in_(all_run_ids))
            )
            # 6. CORTEX nodes referencing execution runs
            try:
                from src.ai.cortex_models import CortexNode
                await self.db.execute(
                    update(CortexNode)
                    .where(CortexNode.execution_run_id.in_(all_run_ids))
                    .values(execution_run_id=None)
                )
            except Exception as e:
                logger.debug(f"CortexNode run_id cleanup skipped: {e}")
            # 7. Artifacts referencing execution runs
            try:
                from src.ai.artifact_models import Artifact
                await self.db.execute(
                    update(Artifact)
                    .where(Artifact.run_id.in_(all_run_ids))
                    .values(run_id=None)
                )
            except Exception as e:
                logger.debug(f"Artifact run_id cleanup skipped: {e}")
            
            # ── Delete execution runs (children first, then parents) ──
            if len(all_run_ids) > len(direct_run_ids):
                child_only = [r for r in all_run_ids if r not in set(direct_run_ids)]
                await self.db.execute(
                    delete(ExecutionRun).where(ExecutionRun.id.in_(child_only))
                )
            await self.db.execute(
                delete(ExecutionRun).where(ExecutionRun.id.in_(direct_run_ids))
            )

        # ── Delete records that reference hierarchical_entities directly ──
        
        # Episodic memories (entity_id FK — catch any not already deleted via run_id)
        await self.db.execute(
            delete(EpisodicMemory).where(EpisodicMemory.entity_id.in_(all_entity_ids))
        )
        
        # CORTEX trees (entity_id FK) — cascade deletes cortex_nodes via relationship
        try:
            from src.ai.cortex_models import CortexTree
            await self.db.execute(
                delete(CortexTree).where(CortexTree.entity_id.in_(all_entity_ids))
            )
        except Exception as e:
            logger.debug(f"CortexTree cleanup skipped: {e}")
        
        # Artifacts (agent_id / campaign_id FK) — nullify, don't delete files
        try:
            from src.ai.artifact_models import Artifact
            await self.db.execute(
                update(Artifact)
                .where(Artifact.agent_id.in_(all_entity_ids))
                .values(agent_id=None)
            )
            await self.db.execute(
                update(Artifact)
                .where(Artifact.campaign_id.in_(all_entity_ids))
                .values(campaign_id=None)
            )
        except Exception as e:
            logger.debug(f"Artifact entity ref cleanup skipped: {e}")
        
        # Call logs (agent_id FK) — nullify
        try:
            from src.ai.artifact_models import CallLog
            await self.db.execute(
                update(CallLog)
                .where(CallLog.agent_id.in_(all_entity_ids))
                .values(agent_id=None)
            )
        except Exception as e:
            logger.debug(f"CallLog cleanup skipped: {e}")
        
        # Documents — unlink from entity
        await self.db.execute(
            update(Document).where(Document.entity_id.in_(all_entity_ids)).values(entity_id=None)
        )
        
        # Other entities referencing this as template_source_id — nullify
        await self.db.execute(
            update(HierarchicalEntity)
            .where(HierarchicalEntity.template_source_id.in_(all_entity_ids))
            .values(template_source_id=None)
        )
        
        # ── Delete entities (children first, then root) ──
        # Reverse order: deepest descendants first
        for eid in reversed(all_entity_ids):
            e_result = await self.db.execute(
                select(HierarchicalEntity).where(HierarchicalEntity.id == eid)
            )
            e_obj = e_result.scalar_one_or_none()
            if e_obj:
                await self.db.delete(e_obj)
        
        await self.db.commit()
        logger.info(f"delete_entity: successfully deleted entity {entity_id} and {len(all_entity_ids)-1} children")

    # Execution
    async def trigger_execution(self, execution_in: ExecutionRunCreate, company_id: UUID, user_id: UUID = None) -> ExecutionRun:
        # Pre-flight: validate entity exists and belongs to this company
        entity = await self.get_entity(execution_in.entity_id, company_id)

        # For PROCESS entities, validate all child entity references exist
        # within the executing company before allowing execution.
        entity_type_str = entity.type.value if hasattr(entity.type, 'value') else str(entity.type)
        if entity_type_str == "PROCESS":
            await self._validate_process_children(entity, company_id)

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

    async def _validate_process_children(self, entity: HierarchicalEntity, company_id: UUID) -> None:
        """
        Pre-flight check: verify all CHILD_ENTITY_INVOCATION targets exist
        within the executing company.  Raises HTTP 400 if any are missing,
        blocking the entire execution with a descriptive error.
        """
        planning = entity.planning or {}
        static_steps = (planning.get("static_plan") or {}).get("steps", [])

        missing: list[str] = []
        for step in static_steps:
            if step.get("type") != "CHILD_ENTITY_INVOCATION":
                continue
            target_id = (step.get("target") or {}).get("entity_id")
            if not target_id:
                missing.append(f"Step '{step.get('name', '?')}' has no entity_id configured")
                continue
            try:
                child_uuid = UUID(str(target_id))
            except (ValueError, AttributeError):
                missing.append(f"Step '{step.get('name', '?')}' has invalid entity_id '{target_id}'")
                continue
            result = await self.db.execute(
                select(HierarchicalEntity.id).where(
                    HierarchicalEntity.id == child_uuid,
                    HierarchicalEntity.company_id == company_id,
                )
            )
            if not result.scalar_one_or_none():
                missing.append(
                    f"Step '{step.get('name', '?')}' references entity {target_id} "
                    f"which does not exist in your company"
                )

        # Also check hierarchy.children for referenced entities
        hierarchy = entity.hierarchy
        if hierarchy and isinstance(hierarchy, dict):
            for child_ref in hierarchy.get("children", []):
                if isinstance(child_ref, dict):
                    child_id_str = child_ref.get("child_id")
                    if child_id_str:
                        try:
                            child_uuid = UUID(str(child_id_str))
                        except (ValueError, AttributeError):
                            continue
                        result = await self.db.execute(
                            select(HierarchicalEntity.id).where(
                                HierarchicalEntity.id == child_uuid,
                                HierarchicalEntity.company_id == company_id,
                            )
                        )
                        if not result.scalar_one_or_none():
                            child_type = child_ref.get("child_type", "unknown")
                            missing.append(
                                f"Hierarchy child ({child_type}) references entity {child_id_str} "
                                f"which does not exist in your company"
                            )

        if missing:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot execute process '{entity.name}': {len(missing)} child "
                    f"entit{'y' if len(missing) == 1 else 'ies'} not found in your company. "
                    f"Please clone the complete template first.\n"
                    + "\n".join(f"  • {m}" for m in missing)
                ),
            )

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

    async def retry_execution(self, execution_id: UUID, company_id: UUID, user_id: UUID) -> ExecutionRun:
        """
        Create a new execution run that resumes from a FAILED run's state.
        
        The new run inherits:
          - entity_id and input_data from the failed run
          - context_state with completed step IDs (so they are skipped)
          - cortex_tree_id from context_state (so the CORTEX tree is resumed)
          - parent_run_id pointing to the failed run for traceability
        """
        from sqlalchemy.orm import selectinload

        # 1. Load the failed run
        result = await self.db.execute(
            select(ExecutionRun).where(
                ExecutionRun.id == execution_id,
                ExecutionRun.company_id == company_id,
            )
        )
        failed_run = result.scalar_one_or_none()
        if not failed_run:
            raise HTTPException(status_code=404, detail="Execution not found")
        if failed_run.status not in ("FAILED", "COMPLETED"):
            raise HTTPException(status_code=400, detail=f"Only FAILED or COMPLETED runs can be retried (current: {failed_run.status})")

        # 2. Build input_data for the retry run.
        #    If the failed run had a CORTEX tree, pass its ID so the engine
        #    resumes the tree rather than creating a new one.
        retry_input = dict(failed_run.input_data or {})
        ctx = failed_run.context_state or {}
        if "__cortex_tree_id__" in ctx:
            retry_input["cortex_tree_id"] = ctx["__cortex_tree_id__"]

        # 3. Create the retry run
        retry_run = ExecutionRun(
            company_id=company_id,
            user_id=user_id,
            entity_id=failed_run.entity_id,
            input_data=retry_input,
            context_state=ctx,  # Carry forward completed step markers
            parent_run_id=failed_run.id,  # Link for traceability
            status="PENDING",
            trace_id=uuid4(),
        )
        self.db.add(retry_run)
        await self.db.commit()

        # 4. Reload with relationships for response
        result = await self.db.execute(
            select(ExecutionRun)
            .options(
                selectinload(ExecutionRun.entity),
                selectinload(ExecutionRun.child_runs),
                selectinload(ExecutionRun.llm_logs),
                selectinload(ExecutionRun.tool_logs),
                selectinload(ExecutionRun.human_approvals),
            )
            .where(ExecutionRun.id == retry_run.id)
        )
        retry_run = result.scalar_one()

        # 5. Enqueue to arq
        redis = await create_pool(RedisSettings())
        await redis.enqueue_job("run_execution_recursive", str(retry_run.id))
        await redis.close()

        return retry_run

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

    async def convert_to_template(self, entity_id: UUID, company_id: UUID, user_id: UUID) -> HierarchicalEntity:
        """
        Deep-clone an existing entity (and all its children) into a parallel
        template hierarchy (is_template=True).  The originals are left untouched.
        """
        from sqlalchemy.orm import selectinload

        # 1. Load the source entity
        result = await self.db.execute(
            select(HierarchicalEntity)
            .options(selectinload(HierarchicalEntity.execution_runs))
            .where(
                HierarchicalEntity.id == entity_id,
                HierarchicalEntity.company_id == company_id,
            )
        )
        source = result.scalar_one_or_none()
        if not source:
            raise HTTPException(status_code=404, detail="Entity not found")
        if source.is_template:
            raise HTTPException(status_code=400, detail="Entity is already a template")

        # 2. Collect all children recursively (follows BOTH parent_id FK and hierarchy.children JSON)
        async def _collect_children(entity: HierarchicalEntity, visited: set[UUID] | None = None) -> list[HierarchicalEntity]:
            if visited is None:
                visited = set()
            visited.add(entity.id)
            children: list[HierarchicalEntity] = []

            # Path A: entities whose parent_id points to this entity
            res = await self.db.execute(
                select(HierarchicalEntity).where(
                    HierarchicalEntity.parent_id == entity.id,
                    HierarchicalEntity.company_id == company_id,
                )
            )
            for child in res.scalars().all():
                if child.id not in visited:
                    children.append(child)

            # Path B: entity IDs referenced in hierarchy.children JSON
            hierarchy = entity.hierarchy
            if hierarchy and isinstance(hierarchy, dict):
                for child_ref in hierarchy.get("children", []):
                    if isinstance(child_ref, dict):
                        child_id_str = child_ref.get("child_id")
                        if child_id_str:
                            try:
                                child_uuid = UUID(str(child_id_str))
                            except (ValueError, AttributeError):
                                continue
                            if child_uuid not in visited:
                                cres = await self.db.execute(
                                    select(HierarchicalEntity).where(
                                        HierarchicalEntity.id == child_uuid,
                                    )
                                )
                                child_entity = cres.scalar_one_or_none()
                                if child_entity:
                                    children.append(child_entity)

            # Recurse into each child
            grandchildren = []
            for child in children:
                grandchildren.extend(await _collect_children(child, visited))
            return children + grandchildren

        all_children = await _collect_children(source)

        # 3. Clone fields helper
        old_to_new_id: dict[UUID, UUID] = {}

        def _clone_fields(src: HierarchicalEntity) -> dict:
            import copy
            return {
                "name": src.name,
                "display_name": src.display_name,
                "description": src.description,
                "goal": src.goal,
                "type": src.type,
                "version": src.version,
                "status": src.status,
                "tags": copy.deepcopy(src.tags) if src.tags else src.tags,
                "identity": copy.deepcopy(src.identity) if src.identity else src.identity,
                "hierarchy": copy.deepcopy(src.hierarchy) if src.hierarchy else src.hierarchy,
                "logic_gate": copy.deepcopy(src.logic_gate) if src.logic_gate else src.logic_gate,
                "planning": copy.deepcopy(src.planning) if src.planning else src.planning,
                "capabilities": copy.deepcopy(src.capabilities) if src.capabilities else src.capabilities,
                "governance": copy.deepcopy(src.governance) if src.governance else src.governance,
                "io_contract": copy.deepcopy(src.io_contract) if src.io_contract else src.io_contract,
                "observability": copy.deepcopy(src.observability) if src.observability else src.observability,
                "metadata_extensions": copy.deepcopy(src.metadata_extensions) if src.metadata_extensions else src.metadata_extensions,
            }

        # 4. Clone root as template
        root_template = HierarchicalEntity(
            **_clone_fields(source),
            company_id=source.company_id,
            created_by=user_id,
            is_template=True,
            template_source_id=source.id,
            parent_id=None,
        )
        self.db.add(root_template)
        await self.db.flush()
        old_to_new_id[source.id] = root_template.id

        # 5. Clone children in topological order
        for child in all_children:
            new_parent_id = old_to_new_id.get(child.parent_id)
            clone = HierarchicalEntity(
                **_clone_fields(child),
                company_id=source.company_id,
                created_by=user_id,
                is_template=True,
                template_source_id=child.id,
                parent_id=new_parent_id,
            )
            self.db.add(clone)
            await self.db.flush()
            old_to_new_id[child.id] = clone.id

        # 6. Remap internal entity_id references (same logic as clone_template)
        def _remap_uuid(val: str | None) -> str | None:
            if not val:
                return val
            try:
                old_uuid = UUID(str(val))
            except (ValueError, AttributeError):
                return val
            new_uuid = old_to_new_id.get(old_uuid)
            return str(new_uuid) if new_uuid else val

        def _remap_entity_refs(entity: HierarchicalEntity) -> bool:
            modified = False
            planning = entity.planning
            if planning and isinstance(planning, dict):
                static_plan = planning.get("static_plan")
                if static_plan and isinstance(static_plan, dict):
                    for step in static_plan.get("steps", []):
                        target = step.get("target") if isinstance(step, dict) else None
                        if target and isinstance(target, dict):
                            old_eid = target.get("entity_id")
                            if old_eid:
                                new_eid = _remap_uuid(old_eid)
                                if new_eid != old_eid:
                                    target["entity_id"] = new_eid
                                    modified = True
                    if modified:
                        entity.planning = {**planning}
            hierarchy = entity.hierarchy
            if hierarchy and isinstance(hierarchy, dict):
                hierarchy_modified = False
                for child_ref in hierarchy.get("children", []):
                    if isinstance(child_ref, dict):
                        old_cid = child_ref.get("child_id")
                        if old_cid:
                            new_cid = _remap_uuid(old_cid)
                            if new_cid != old_cid:
                                child_ref["child_id"] = new_cid
                                hierarchy_modified = True
                if hierarchy_modified:
                    entity.hierarchy = {**hierarchy}
                    modified = True
            return modified

        all_cloned = [root_template] + [
            (await self.db.execute(
                select(HierarchicalEntity).where(HierarchicalEntity.id == new_id)
            )).scalar_one()
            for new_id in list(old_to_new_id.values())[1:]
        ]
        for cloned_entity in all_cloned:
            if _remap_entity_refs(cloned_entity):
                self.db.add(cloned_entity)

        await self.db.commit()

        # 7. Reload with relationships
        result = await self.db.execute(
            select(HierarchicalEntity)
            .options(selectinload(HierarchicalEntity.execution_runs))
            .where(HierarchicalEntity.id == root_template.id)
        )
        return result.scalar_one()

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

        # 2. Collect all child entities via THREE discovery paths:
        #    A) parent_id FK pointing to this entity (+ is_template filter)
        #    B) hierarchy.children JSON (load by ID directly — trusted reference)
        #    C) planning.static_plan.steps[].target.entity_id for CHILD_ENTITY_INVOCATION
        async def _collect_children(entity: HierarchicalEntity, visited: set[UUID] | None = None) -> list[HierarchicalEntity]:
            if visited is None:
                visited = set()
            visited.add(entity.id)
            children: list[HierarchicalEntity] = []
            seen_ids: set[UUID] = set()

            async def _try_add(child_uuid: UUID):
                """Load an entity by ID and add it if not already visited."""
                if child_uuid in visited or child_uuid in seen_ids:
                    return
                cres = await self.db.execute(
                    select(HierarchicalEntity).where(
                        HierarchicalEntity.id == child_uuid,
                        HierarchicalEntity.is_template == True,
                    )
                )
                child_entity = cres.scalar_one_or_none()
                if child_entity:
                    children.append(child_entity)
                    seen_ids.add(child_uuid)

            # Path A: entities whose parent_id points to this entity
            res = await self.db.execute(
                select(HierarchicalEntity).where(
                    HierarchicalEntity.parent_id == entity.id,
                    HierarchicalEntity.is_template == True,
                )
            )
            for child in res.scalars().all():
                if child.id not in visited:
                    children.append(child)
                    seen_ids.add(child.id)

            # Path B: entity IDs referenced in hierarchy.children JSON
            hierarchy = entity.hierarchy
            if hierarchy and isinstance(hierarchy, dict):
                for child_ref in hierarchy.get("children", []):
                    if isinstance(child_ref, dict):
                        child_id_str = child_ref.get("child_id")
                        if child_id_str:
                            try:
                                await _try_add(UUID(str(child_id_str)))
                            except (ValueError, AttributeError):
                                continue

            # Path C: entity IDs in CHILD_ENTITY_INVOCATION steps
            planning = entity.planning
            if planning and isinstance(planning, dict):
                for step in (planning.get("static_plan") or {}).get("steps", []):
                    if step.get("type") == "CHILD_ENTITY_INVOCATION":
                        eid = (step.get("target") or {}).get("entity_id")
                        if eid:
                            try:
                                await _try_add(UUID(str(eid)))
                            except (ValueError, AttributeError):
                                continue

            # Recurse into each child
            grandchildren = []
            for child in children:
                grandchildren.extend(await _collect_children(child, visited))
            return children + grandchildren

        all_children = await _collect_children(template)
        logger.info(
            f"clone_template: discovered {len(all_children)} child entities "
            f"for template '{template.name}' (id={template.id})"
        )

        # 3. Clone root template
        old_to_new_id: dict[UUID, UUID] = {}

        def _clone_fields(src: HierarchicalEntity) -> dict:
            """Extract clonable fields from a template entity.
            
            IMPORTANT: JSON/dict fields must be deep-copied to prevent
            shared references between the template and clone. SQLAlchemy
            returns the same dict object for JSON columns, so without
            deep-copy, the remap step would mutate template data.
            """
            import copy
            return {
                "name": src.name,
                "display_name": src.display_name,
                "description": src.description,
                "goal": src.goal,
                "type": src.type,
                "version": src.version,
                "status": src.status,
                "tags": copy.deepcopy(src.tags) if src.tags else src.tags,
                "identity": copy.deepcopy(src.identity) if src.identity else src.identity,
                "hierarchy": copy.deepcopy(src.hierarchy) if src.hierarchy else src.hierarchy,
                "logic_gate": copy.deepcopy(src.logic_gate) if src.logic_gate else src.logic_gate,
                "planning": copy.deepcopy(src.planning) if src.planning else src.planning,
                "capabilities": copy.deepcopy(src.capabilities) if src.capabilities else src.capabilities,
                "governance": copy.deepcopy(src.governance) if src.governance else src.governance,
                "io_contract": copy.deepcopy(src.io_contract) if src.io_contract else src.io_contract,
                "observability": copy.deepcopy(src.observability) if src.observability else src.observability,
                "metadata_extensions": copy.deepcopy(src.metadata_extensions) if src.metadata_extensions else src.metadata_extensions,
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

        # Auto-populate io_contract.input_schema from prompt template variables
        self._auto_generate_input_schema(root_clone)

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

        # 5. Post-clone: remap internal entity_id references using old_to_new_id
        import copy as _copy
        from sqlalchemy.orm.attributes import flag_modified

        logger.info(
            f"clone_template: old_to_new_id mapping ({len(old_to_new_id)} entries): "
            + ", ".join(f"{str(k)[:8]}→{str(v)[:8]}" for k, v in old_to_new_id.items())
        )

        def _remap_uuid(val: str | None) -> str | None:
            """If val is a UUID string that exists in old_to_new_id, return the new UUID."""
            if not val:
                return val
            try:
                old_uuid = UUID(str(val))
            except (ValueError, AttributeError):
                return val
            new_uuid = old_to_new_id.get(old_uuid)
            if new_uuid:
                logger.debug(f"  remap: {str(old_uuid)[:8]}.. → {str(new_uuid)[:8]}..")
            return str(new_uuid) if new_uuid else val

        def _remap_entity_refs(entity: HierarchicalEntity) -> bool:
            """Remap entity_id references inside planning and hierarchy JSON. Returns True if modified."""
            modified = False

            # Remap planning.static_plan.steps[].target.entity_id
            planning = _copy.deepcopy(entity.planning) if entity.planning else None
            if planning and isinstance(planning, dict):
                static_plan = planning.get("static_plan")
                if static_plan and isinstance(static_plan, dict):
                    steps = static_plan.get("steps", [])
                    for step in steps:
                        target = step.get("target") if isinstance(step, dict) else None
                        if target and isinstance(target, dict):
                            old_eid = target.get("entity_id")
                            if old_eid:
                                new_eid = _remap_uuid(old_eid)
                                if new_eid != old_eid:
                                    target["entity_id"] = new_eid
                                    modified = True
                                    logger.info(f"  Remapped step entity_id: {old_eid[:12]}.. → {new_eid[:12]}..")
                    if modified:
                        entity.planning = planning
                        flag_modified(entity, "planning")

            # Remap hierarchy.children[].child_id
            hierarchy = _copy.deepcopy(entity.hierarchy) if entity.hierarchy else None
            if hierarchy and isinstance(hierarchy, dict):
                children = hierarchy.get("children", [])
                hierarchy_modified = False
                for child_ref in children:
                    if isinstance(child_ref, dict):
                        old_cid = child_ref.get("child_id")
                        if old_cid:
                            new_cid = _remap_uuid(old_cid)
                            if new_cid != old_cid:
                                child_ref["child_id"] = new_cid
                                hierarchy_modified = True
                                logger.info(f"  Remapped hierarchy child_id: {old_cid[:12]}.. → {new_cid[:12]}..")
                if hierarchy_modified:
                    entity.hierarchy = hierarchy
                    flag_modified(entity, "hierarchy")
                    modified = True

            return modified

        # Apply remapping to every cloned entity
        # We must reload each clone from DB to get the flushed state,
        # then apply remap on independent copies of the JSON data.
        all_cloned = [root_clone]
        for new_id in list(old_to_new_id.values())[1:]:  # skip root_clone
            result = await self.db.execute(
                select(HierarchicalEntity).where(HierarchicalEntity.id == new_id)
            )
            all_cloned.append(result.scalar_one())

        for cloned_entity in all_cloned:
            was_modified = _remap_entity_refs(cloned_entity)
            logger.info(
                f"clone_template: remap '{cloned_entity.name}' (id={str(cloned_entity.id)[:8]}..): "
                f"modified={was_modified}"
            )
            if was_modified:
                self.db.add(cloned_entity)

        await self.db.commit()

        # 6. Reload with relationships
        result = await self.db.execute(
            select(HierarchicalEntity)
            .options(selectinload(HierarchicalEntity.execution_runs))
            .where(HierarchicalEntity.id == root_clone.id)
        )

        logger.info(
            f"clone_template: successfully cloned template '{template.name}' → "
            f"'{root_clone.name}' (root={root_clone.id}, children={len(all_children)})"
        )
        return result.scalar_one()

    @staticmethod
    def _auto_generate_input_schema(entity: HierarchicalEntity) -> None:
        """
        Scan prompt templates in the entity's static plan for {{variable}}
        placeholders and auto-populate io_contract.input_schema if it is
        empty.  Skips internal step references (step_1, step_2, etc.) and
        system variables (__cortex_tree_id__, etc.).

        Also scans the entity's goal field for {{variable}} patterns.
        """
        io_contract = entity.io_contract or {}
        input_schema = io_contract.get("input_schema") or {}
        existing_props = input_schema.get("properties") or {}

        # If io_contract already has properties defined, don't override
        if existing_props:
            return

        # Scan all prompt templates in the static plan
        planning = entity.planning or {}
        static_steps = (planning.get("static_plan") or {}).get("steps", [])

        discovered_vars: set[str] = set()
        step_ref_pattern = re.compile(r'^step_\d+')

        for step in static_steps:
            prompt = (step.get("target") or {}).get("prompt_template", "")
            if isinstance(prompt, dict):
                prompt = json.dumps(prompt, default=str)
            if not isinstance(prompt, str):
                continue

            for match in re.finditer(r'\{\{(\w+)\}\}', prompt):
                var_name = match.group(1)
                # Skip internal step references and system variables
                if not step_ref_pattern.match(var_name) and not var_name.startswith("__"):
                    discovered_vars.add(var_name)

        # Also scan the entity's goal for variables
        if entity.goal:
            for match in re.finditer(r'\{\{(\w+)\}\}', entity.goal):
                var_name = match.group(1)
                if not step_ref_pattern.match(var_name) and not var_name.startswith("__"):
                    discovered_vars.add(var_name)

        if discovered_vars:
            properties = {
                var: {"type": "string", "description": var.replace("_", " ").title()}
                for var in sorted(discovered_vars)
            }
            entity.io_contract = {
                **io_contract,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": list(sorted(discovered_vars)),
                },
            }
            logger.info(
                f"Auto-generated input_schema for entity '{entity.name}' "
                f"with variables: {sorted(discovered_vars)}"
            )
