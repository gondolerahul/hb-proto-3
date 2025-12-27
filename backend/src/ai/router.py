from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List, Optional
from src.common.database import get_db
from src.auth.dependencies import get_current_user, get_current_user_from_query
from src.auth.models import User
from src.ai.schemas import (
    HierarchicalEntityCreate, HierarchicalEntityUpdate, HierarchicalEntityResponse, 
    ExecutionRunCreate, ExecutionRunResponse, ExecutionRunSummary, EntityType,
    DocumentResponse, DocumentSearchResult
)
from src.ai.service import AIService

router = APIRouter(prefix="/ai", tags=["AI Hierarchical Agent Platform"])

# --- Entities ---
@router.post("/entities", response_model=HierarchicalEntityResponse)
async def create_entity(
    entity_in: HierarchicalEntityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.create_entity(entity_in, current_user.company_id)

@router.get("/entities", response_model=List[HierarchicalEntityResponse])
async def list_entities(
    type: Optional[EntityType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.get_entities(current_user.company_id, type)

@router.get("/entities/{entity_id}", response_model=HierarchicalEntityResponse)
async def get_entity(
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.get_entity(entity_id, current_user.company_id)

@router.put("/entities/{entity_id}", response_model=HierarchicalEntityResponse)
async def update_entity(
    entity_id: UUID,
    entity_in: HierarchicalEntityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.update_entity(entity_id, entity_in, current_user.company_id)

@router.delete("/entities/{entity_id}")
async def delete_entity(
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    await service.delete_entity(entity_id, current_user.company_id)
    return {"status": "success"}

# --- Dashboard ---
@router.get("/stats", response_model=dict)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.get_dashboard_stats(current_user.company_id)

# --- Executions ---
@router.post("/execute", response_model=ExecutionRunResponse)
async def trigger_execution(
    execution_in: ExecutionRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.trigger_execution(execution_in, current_user.company_id)

@router.get("/executions", response_model=List[ExecutionRunSummary])
async def list_executions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.get_executions(current_user.company_id)

@router.get("/executions/{execution_id}", response_model=ExecutionRunResponse)
async def get_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    execution = await service.get_execution(execution_id, current_user.company_id)
    return execution

@router.get("/executions/{execution_id}/stream")
async def stream_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_query)
):
    # Verify access
    service = AIService(db)
    await service.get_execution(execution_id, current_user.company_id)
    
    from fastapi.responses import StreamingResponse
    import redis.asyncio as redis
    from src.common.config import settings
    import asyncio

    async def event_generator():
        r = redis.from_url(settings.REDIS_URL or "redis://localhost:6379")
        pubsub = r.pubsub()
        channel = f"execution:{execution_id}"
        await pubsub.subscribe(channel)
        
        try:
            # Send initial connection message
            yield "data: {\"status\": \"connected\"}\n\n"
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"].decode("utf-8")
                    yield f"data: {data}\n\n"
                    if "\"status\": \"COMPLETED\"" in data or f"\"status\": \"FAILED\"" in data:
                        break
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await r.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- HITL (Human-In-The-Loop) ---
@router.get("/approvals/pending", response_model=List[dict])
async def list_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    approvals = await service.get_pending_approvals(current_user.company_id)
    return [
        {
            "id": str(a.id),
            "run_id": str(a.run_id),
            "checkpoint_trigger": a.checkpoint_trigger,
            "status": a.status,
            "requested_at": a.requested_at
        }
        for a in approvals
    ]

@router.post("/approvals/{approval_id}/respond")
async def respond_to_approval(
    approval_id: UUID,
    status: str, # APPROVED | REJECTED
    notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    await service.respond_to_approval(approval_id, status, current_user.id, notes)
    return {"status": "success"}

# --- Tools ---
@router.get("/tools", response_model=list[dict])
async def list_tools(
    current_user: User = Depends(get_current_user)
):
    from src.ai.tools import ToolRegistry
    return ToolRegistry.list_tools()

# --- Documents ---
@router.post("/documents/upload", response_model=dict)
async def upload_document(
    file: UploadFile = File(...),
    entity_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Read file content
    file_content = await file.read()
    
    # Get file extension
    file_type = file.filename.split('.')[-1].lower() if '.' in file.filename else 'txt'
    
    service = AIService(db)
    document = await service.upload_document(
        file_content=file_content,
        filename=file.filename,
        file_type=file_type,
        company_id=current_user.company_id,
        entity_id=entity_id
    )
    return {"id": str(document.id), "status": document.upload_status}

@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    entity_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.get_documents(current_user.company_id, entity_id)

@router.post("/documents/search", response_model=List[dict])
async def search_documents(
    query: str,
    entity_id: Optional[UUID] = None,
    top_k: int = 5,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    results = await service.search_documents(
        query=query,
        company_id=current_user.company_id,
        entity_id=entity_id,
        top_k=top_k
    )
    return [
        {
            "chunk_id": str(r.chunk_id),
            "document_id": str(r.document_id),
            "filename": r.filename,
            "content": r.content,
            "similarity": float(r.similarity)
        }
        for r in results
    ]
