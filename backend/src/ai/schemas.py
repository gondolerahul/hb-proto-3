from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from enum import Enum

class EntityType(str, Enum):
    ACTION = "ACTION"
    SKILL = "SKILL"
    AGENT = "AGENT"
    PROCESS = "PROCESS"

class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REPAIRING = "REPAIRING"

# Model Config Schema
class ModelConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    tools: Optional[List[str]] = []

# Hierarchical Entity Schemas
class HierarchicalEntityBase(BaseModel):
    name: str
    description: Optional[str] = None
    type: EntityType
    static_plan: Optional[Dict[str, Any]] = None
    llm_config: Optional[ModelConfig] = None
    toolkit: Optional[List[Dict[str, Any]]] = None
    is_active: bool = True

class HierarchicalEntityCreate(HierarchicalEntityBase):
    parent_id: Optional[UUID] = None

class HierarchicalEntityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    static_plan: Optional[Dict[str, Any]] = None
    llm_config: Optional[ModelConfig] = None
    toolkit: Optional[List[Dict[str, Any]]] = None
    is_active: Optional[bool] = None
    parent_id: Optional[UUID] = None

class HierarchicalEntityResponse(HierarchicalEntityBase):
    id: UUID
    company_id: UUID
    parent_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Execution Run Schemas
class ExecutionRunCreate(BaseModel):
    entity_id: UUID
    input_data: Dict[str, Any]

class LLMInteractionLogResponse(BaseModel):
    id: UUID
    model_provider: str
    model_name: str
    input_prompt: str
    output_response: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True

class ExecutionRunSummary(BaseModel):
    id: UUID
    entity_id: UUID
    parent_run_id: Optional[UUID]
    company_id: UUID
    status: RunStatus
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    entity: Optional[HierarchicalEntityResponse] = None

    class Config:
        from_attributes = True

class ExecutionRunResponse(ExecutionRunSummary):
    input_data: Optional[Dict[str, Any]]
    dynamic_plan: Optional[Dict[str, Any]]
    result_data: Optional[Dict[str, Any]]
    context_state: Optional[Dict[str, Any]]
    llm_logs: List[LLMInteractionLogResponse] = []
    child_runs: List["ExecutionRunResponse"] = []

ExecutionRunResponse.model_rebuild()

# Document Schemas
class DocumentUploadResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    upload_status: str
    created_at: datetime

    class Config:
        from_attributes = True

class DocumentResponse(BaseModel):
    id: UUID
    company_id: UUID
    entity_id: Optional[UUID]
    filename: str
    file_type: str
    file_size: Optional[str]
    upload_status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class DocumentSearchRequest(BaseModel):
    query: str
    entity_id: Optional[UUID] = None
    top_k: int = 5

class DocumentSearchResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    content: str
    similarity: float

# Agent Schemas
class AgentBase(BaseModel):
    name: str
    role: str
    llm_config: ModelConfig
    is_active: bool = True

class AgentCreate(AgentBase):
    pass

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    llm_config: Optional[ModelConfig] = None
    is_active: Optional[bool] = None

class AgentResponse(AgentBase):
    id: UUID
    company_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Workflow Schemas
class WorkflowNode(BaseModel):
    id: str
    type: str  # agent, tool, input
    config: Dict[str, Any]

class WorkflowEdge(BaseModel):
    source: str
    target: str

class WorkflowDAG(BaseModel):
    nodes: List[WorkflowNode]
    edges: List[WorkflowEdge]

class WorkflowBase(BaseModel):
    name: str
    dag_structure: WorkflowDAG
    is_active: bool = True

class WorkflowCreate(WorkflowBase):
    pass

class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    dag_structure: Optional[WorkflowDAG] = None
    is_active: Optional[bool] = None

class WorkflowResponse(WorkflowBase):
    id: UUID
    company_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Execution Schemas
class ExecutionCreate(BaseModel):
    agent_id: Optional[UUID] = None
    workflow_id: Optional[UUID] = None
    input_data: Dict[str, Any]

class ExecutionResponse(BaseModel):
    id: UUID
    status: str
    result_data: Optional[Dict[str, Any]]
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

# Document Schemas
class DocumentUploadResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    upload_status: str
    created_at: datetime

    class Config:
        from_attributes = True

class DocumentResponse(BaseModel):
    id: UUID
    company_id: UUID
    agent_id: Optional[UUID]
    filename: str
    file_type: str
    file_size: Optional[str]
    upload_status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class DocumentSearchRequest(BaseModel):
    query: str
    agent_id: Optional[UUID] = None
    top_k: int = 5

class DocumentSearchResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    content: str
    similarity: float
