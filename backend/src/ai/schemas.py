from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID

# Model Config Schema
class ModelConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    tools: Optional[List[str]] = []  # List of enabled tool names

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
