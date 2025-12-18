from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from src.common.database import get_db
from src.auth.dependencies import get_current_user, get_current_user_from_query
from src.auth.models import User
from src.ai.schemas import AgentCreate, AgentUpdate, AgentResponse, WorkflowCreate, WorkflowUpdate, WorkflowResponse, ExecutionCreate, ExecutionResponse
from src.ai.service import AIService

router = APIRouter(prefix="/ai", tags=["AI Agent Builder"])

@router.post("/agents", response_model=AgentResponse)
async def create_agent(
    agent_in: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.create_agent(agent_in, current_user.tenant_id)

@router.get("/stats", response_model=dict)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.get_dashboard_stats(current_user.tenant_id)

@router.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.get_agents(current_user.tenant_id)

@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.get_agent(agent_id, current_user.tenant_id)

@router.put("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    agent_in: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.update_agent(agent_id, agent_in, current_user.tenant_id)

@router.post("/workflows", response_model=WorkflowResponse)
async def create_workflow(
    workflow_in: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from src.ai.dag_validator import DAGValidator
    
    # Validate DAG structure
    dag = workflow_in.dag_structure
    if dag.nodes and dag.edges:
        DAGValidator.validate_dag(
            [{"id": n.id, **n.model_dump()} for n in dag.nodes],
            [{"source": e.source, "target": e.target} for e in dag.edges]
        )
    
    service = AIService(db)
    return await service.create_workflow(workflow_in, current_user.tenant_id)

@router.get("/workflows", response_model=list[WorkflowResponse])
async def list_workflows(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.get_workflows(current_user.tenant_id)

@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.get_workflow(workflow_id, current_user.tenant_id)

@router.put("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: UUID,
    workflow_in: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from src.ai.dag_validator import DAGValidator

    # Validate DAG structure if provided
    if workflow_in.dag_structure:
        dag = workflow_in.dag_structure
        if dag.nodes and dag.edges:
            # We need to construct the node dicts carefully as validation expects
            DAGValidator.validate_dag(
                [{"id": n.id, **n.model_dump()} for n in dag.nodes],
                [{"source": e.source, "target": e.target} for e in dag.edges]
            )

    service = AIService(db)
    return await service.update_workflow(workflow_id, workflow_in, current_user.tenant_id)

@router.post("/execute", response_model=ExecutionResponse)
async def trigger_execution(
    execution_in: ExecutionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.trigger_execution(execution_in, current_user.tenant_id)

@router.get("/executions", response_model=list[ExecutionResponse])
async def list_executions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.get_executions(current_user.tenant_id)

@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    return await service.get_execution(execution_id, current_user.tenant_id)

@router.get("/executions/{execution_id}/stream")
async def stream_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_query)
):
    # Verify access
    service = AIService(db)
    await service.get_execution(execution_id, current_user.tenant_id)
    
    from fastapi.responses import StreamingResponse
    import redis.asyncio as redis
    from src.common.config import settings
    import asyncio

    async def event_generator():
        r = redis.from_url(settings.REDIS_URL)
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
                    if "\"status\": \"completed\"" in data or "\"status\": \"failed\"" in data:
                        break
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await r.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/tools", response_model=list[dict])
async def list_tools(
    current_user: User = Depends(get_current_user)
):
    from src.ai.tools import ToolRegistry
    return ToolRegistry.list_tools()

@router.post("/documents/upload", response_model=dict)
async def upload_document(
    file: UploadFile = File(...),
    agent_id: UUID = None,
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
        tenant_id=current_user.tenant_id,
        agent_id=agent_id
    )
    return {"id": str(document.id), "status": document.upload_status}

@router.get("/documents")
async def list_documents(
    agent_id: UUID = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    documents = await service.get_documents(current_user.tenant_id, agent_id)
    return documents

@router.post("/documents/search")
async def search_documents(
    query: str,
    agent_id: UUID = None,
    top_k: int = 5,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = AIService(db)
    results = await service.search_documents(
        query=query,
        tenant_id=current_user.tenant_id,
        agent_id=agent_id,
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
