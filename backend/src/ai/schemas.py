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

# Nested Entity Schemas

class EntityStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"

class RelationshipType(str, Enum):
    SEQUENTIAL = "SEQUENTIAL"
    PARALLEL = "PARALLEL"
    CONDITIONAL = "CONDITIONAL"

class ReasoningMode(str, Enum):
    REACT = "REACT"
    CHAIN_OF_THOUGHT = "CHAIN_OF_THOUGHT"
    REFLECTION = "REFLECTION"
    TREE_OF_THOUGHTS = "TREE_OF_THOUGHTS"

class BackoffStrategy(str, Enum):
    LINEAR = "LINEAR"
    EXPONENTIAL = "EXPONENTIAL"
    NONE = "NONE"

class ValidationType(str, Enum):
    REGEX = "REGEX"
    SCHEMA = "SCHEMA"
    LLM_JUDGE = "LLM_JUDGE"
    FUNCTION = "FUNCTION"

class StepType(str, Enum):
    THOUGHT = "THOUGHT"
    ACTION = "ACTION"
    TOOL_CALL = "TOOL_CALL"
    CHILD_ENTITY_INVOCATION = "CHILD_ENTITY_INVOCATION"

class PersonaExample(BaseModel):
    scenario: str
    ideal_response: str

class Persona(BaseModel):
    system_prompt: str
    examples: List[PersonaExample] = []
    behavioral_constraints: List[str] = []

class HierarchyChildCondition(BaseModel):
    enabled: bool = False
    expression: Optional[str] = None
    description: Optional[str] = None

class HierarchyChild(BaseModel):
    child_id: UUID
    child_type: EntityType
    relationship: RelationshipType
    condition: Optional[HierarchyChildCondition] = None

class Hierarchy(BaseModel):
    parent_id: Optional[UUID] = None
    children: List[HierarchyChild] = []
    is_atomic: bool = True
    composition_depth: int = 0

class ReasoningConfig(BaseModel):
    model_provider: str
    model_name: str
    model_version: Optional[str] = None
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: Optional[int] = None
    reasoning_mode: ReasoningMode = ReasoningMode.REACT

class RetryPolicy(BaseModel):
    max_retries: int = 3
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    backoff_multiplier: float = 2.0
    retry_on: List[str] = ["TOOL_FAILURE", "LLM_ERROR", "TIMEOUT"]

class SuccessCriterion(BaseModel):
    criterion: str
    validation_type: ValidationType
    validator: str

class ReviewMechanism(BaseModel):
    enabled: bool = False
    review_prompt: Optional[str] = None
    success_criteria: List[SuccessCriterion] = []
    on_failure: str = "RETRY" # RETRY | ESCALATE | ABORT

class LogicGate(BaseModel):
    reasoning_config: ReasoningConfig
    retry_policy: RetryPolicy = RetryPolicy()
    review_mechanism: ReviewMechanism = ReviewMechanism()

class ExitCondition(BaseModel):
    condition: str
    next_step: Any # Integer | 'END' | 'ESCALATE'

class PlanStepTarget(BaseModel):
    entity_id: Optional[UUID] = None
    tool_id: Optional[str] = None
    prompt_template: Optional[str] = None

class PlanStep(BaseModel):
    step_id: UUID
    order: int
    name: str
    description: Optional[str] = None
    type: StepType
    target: PlanStepTarget
    required: bool = True
    exit_conditions: List[ExitCondition] = []

class StaticPlan(BaseModel):
    enabled: bool = True
    steps: List[PlanStep] = []
    fallback_behavior: str = "ADAPTIVE" # STRICT | ADAPTIVE | DYNAMIC_ONLY

class AllowedDeviations(BaseModel):
    can_add_steps: bool = True
    can_skip_optional_steps: bool = True
    can_reorder_steps: bool = False
    can_change_tools: bool = False

class DynamicPlanning(BaseModel):
    enabled: bool = False
    planning_prompt: Optional[str] = None
    constraints: List[str] = []
    reconciliation_strategy: str = "HYBRID" # STATIC_PRIORITY | DYNAMIC_PRIORITY | HYBRID
    allowed_deviations: AllowedDeviations = AllowedDeviations()

class ConvergenceCriterion(BaseModel):
    metric: str
    threshold: float
    operator: str # GT | LT | EQ | GTE | LTE

class LoopControl(BaseModel):
    max_iterations: Optional[int] = 1
    convergence_criteria: List[ConvergenceCriterion] = []
    iteration_context_mode: str = "FULL_HISTORY" # FULL_HISTORY | SUMMARIZED | LAST_N
    summary_every_n_iterations: Optional[int] = None

class Planning(BaseModel):
    static_plan: StaticPlan = StaticPlan()
    dynamic_planning: DynamicPlanning = DynamicPlanning()
    loop_control: LoopControl = LoopControl()

class ToolAuth(BaseModel):
    type: str # NONE | API_KEY | OAUTH2 | SERVICE_ACCOUNT
    credentials_ref: Optional[str] = None

class ToolDefinition(BaseModel):
    tool_id: str
    name: str
    description: str
    provider: str
    authentication: ToolAuth = ToolAuth(type="NONE")
    function_schema: Dict[str, Any]
    permissions: str = "READ" # READ | WRITE | EXECUTE
    sandbox_mode: bool = False

class MemoryConfig(BaseModel):
    enabled: bool = False
    scope: str = "SESSION" # SESSION | ENTITY | GLOBAL
    storage_backend: str = "POSTGRES_JSONB"
    retention_policy: Dict[str, Any] = {}
    access_pattern: str = "RECENT_N"

class ArtifactHandling(BaseModel):
    store_large_objects: bool = True
    artifact_reference_mode: str = "REFERENCE" # INLINE | REFERENCE | SUMMARY

class ContextEngineering(BaseModel):
    max_context_tokens: int = 4096
    context_priority: List[str] = ["SYSTEM_PROMPT", "STATIC_PLAN", "USER_INPUT"]
    artifact_handling: ArtifactHandling = ArtifactHandling()

class Capabilities(BaseModel):
    tools: List[ToolDefinition] = []
    memory: MemoryConfig = MemoryConfig()
    context_engineering: ContextEngineering = ContextEngineering()

class Governance(BaseModel):
    max_cost_usd: Optional[float] = None
    timeout_ms: int = 60000
    max_recursion_depth: int = 5
    hitl_checkpoints: List[Dict[str, Any]] = []

class IOContract(BaseModel):
    input_schema: Dict[str, Any] = {"type": "object", "properties": {}}
    output_schema: Dict[str, Any] = {"type": "object", "properties": {}}

class Observability(BaseModel):
    log_level: str = "INFO"
    log_thoughts: bool = True
    track_cost: bool = True

# Hierarchical Entity Schemas
class HierarchicalEntityBase(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    type: EntityType
    version: str = "1.0.0"
    status: EntityStatus = EntityStatus.ACTIVE
    tags: List[str] = []
    
    identity: Optional[Persona] = None
    hierarchy: Optional[Hierarchy] = None
    logic_gate: Optional[LogicGate] = None
    planning: Optional[Planning] = None
    capabilities: Optional[Capabilities] = None
    governance: Optional[Governance] = None
    io_contract: Optional[IOContract] = None
    observability: Optional[Observability] = None
    metadata_extensions: Optional[Dict[str, Any]] = None

    # Legacy fields
    static_plan: Optional[Dict[str, Any]] = None
    llm_config: Optional[Any] = None
    is_active: bool = True

class HierarchicalEntityCreate(HierarchicalEntityBase):
    parent_id: Optional[UUID] = None

class HierarchicalEntityUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[EntityStatus] = None
    version: Optional[str] = None
    identity: Optional[Persona] = None
    hierarchy: Optional[Hierarchy] = None
    logic_gate: Optional[LogicGate] = None
    planning: Optional[Planning] = None
    capabilities: Optional[Capabilities] = None
    governance: Optional[Governance] = None
    io_contract: Optional[IOContract] = None
    observability: Optional[Observability] = None
    metadata_extensions: Optional[Dict[str, Any]] = None
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
    cost_usd: float = 0.0
    reasoning_mode: Optional[str] = None
    log_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ToolInteractionLogResponse(BaseModel):
    id: UUID
    tool_id: str
    tool_name: str
    provider: Optional[str] = None
    input_parameters: Optional[Dict[str, Any]] = None
    output_result: Optional[Dict[str, Any]] = None
    success: bool
    error_message: Optional[str] = None
    latency_ms: Optional[int] = None
    log_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True

class HumanApprovalResponse(BaseModel):
    id: UUID
    checkpoint_trigger: str
    status: str
    requested_by: Optional[str] = None
    context_snapshot: Optional[Dict[str, Any]] = None
    reviewer_notes: Optional[str] = None
    requested_at: datetime
    responded_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ExecutionRunSummary(BaseModel):
    id: UUID
    entity_id: UUID
    parent_run_id: Optional[UUID]
    company_id: UUID
    status: RunStatus
    error_message: Optional[str]
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    execution_time_ms: Optional[int] = None
    trace_id: Optional[UUID] = None
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
    tool_logs: List[ToolInteractionLogResponse] = []
    human_approvals: List[HumanApprovalResponse] = []
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
