from pydantic import BaseModel, field_validator
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
    # CORTEX step types
    NAVIGATE = "NAVIGATE"
    READ = "READ"
    WRITE = "WRITE"
    RECURSE = "RECURSE"
    AWAIT_CHILDREN = "AWAIT_CHILDREN"

class PersonaExample(BaseModel):
    scenario: str
    ideal_response: str


# ---------------------------------------------------------------------------
# P2.1 — Standardized Persona Schema Hierarchy
# Replaces the loosely-typed JSON blob in HierarchicalEntity.identity.
# ---------------------------------------------------------------------------

class VoiceConfig(BaseModel):
    """
    Voice identity parameters for Gemini Live API.
    Applied when the agent is used in a real-time voice/streaming session.
    """
    voice_name: str = "Aoede"
    """
    Prebuilt Gemini voice. Options:
    Puck, Charon, Kore, Fenrir, Aoede, Orbit, Zephyr, Leda,
    Orus, Rigel, Schedar, Pulcherrima, Achird, Zubenelgenubi,
    Vindemiatrix, Sadachbia, Sadaltager, Sulafat
    """
    language_code: str = "en-US"   # BCP-47 language tag
    speaking_rate: float = 1.0     # 0.25 – 4.0  (1.0 = normal)
    pitch: float = 0.0             # -20.0 to +20.0 semitones
    # Future: custom voice clone reference
    custom_voice_id: Optional[str] = None


class PersonalityMatrix(BaseModel):
    """
    Behavioral fingerprint injected into the system prompt at runtime.
    Each dimension controls a specific tonal / stylistic aspect.
    """
    tone: str = "professional"        # e.g. friendly, formal, empathetic, assertive
    verbosity: str = "concise"        # concise | moderate | verbose
    empathy_level: float = 0.7        # 0.0 (robotic) → 1.0 (highly empathetic)
    humor_level: float = 0.2          # 0.0 (none) → 1.0 (frequent humor)
    formality: str = "semi-formal"    # formal | semi-formal | casual
    decision_confidence: float = 0.8  # Confidence threshold before escalating to human


class AgentPersona(BaseModel):
    """
    Canonical, standardized persona for HierarchicalEntity.identity.
    This replaces the old free-form JSON with a typed, validated structure.

    Usage:
        entity.identity = AgentPersona(...).model_dump()
    """
    # Core identity
    name: str = "AI Assistant"
    role: str = "AI Assistant"
    bio: Optional[str] = None

    # Visual identity (for UI and future multi-modal interactions)
    profile_image_url: Optional[str] = None
    profile_image_thumbnail_url: Optional[str] = None

    # Behavioral fingerprint
    personality: PersonalityMatrix = PersonalityMatrix()

    # Voice identity (for Gemini Live sessions)
    voice: VoiceConfig = VoiceConfig()

    # Prompt engineering
    system_prompt: str = ""
    behavioral_constraints: List[str] = []
    few_shot_examples: List[PersonaExample] = []

    # Dynamic injection hooks
    greeting_template: Optional[str] = None    # First utterance template
    escalation_message: Optional[str] = None   # What to say when escalating to human
    closing_message: Optional[str] = None      # End-of-call closing statement


class Persona(BaseModel):
    """Legacy persona model — kept for backward compatibility. Prefer AgentPersona."""
    system_prompt: str
    examples: List[PersonaExample] = []
    behavioral_constraints: List[str] = []
    few_shot_examples: List[Dict[str, str]] = []


class HierarchyChildCondition(BaseModel):
    enabled: bool = False
    expression: Optional[str] = None
    description: Optional[str] = None

class HierarchyChild(BaseModel):
    child_id: Optional[str] = None  # Accept string IDs from frontend
    child_type: Optional[str] = None  # Accept string type from frontend
    relationship: Optional[str] = None  # Accept string relationship from frontend
    condition: Optional[HierarchyChildCondition] = None

class Hierarchy(BaseModel):
    parent_id: Optional[UUID] = None
    children: List[HierarchyChild] = []
    is_atomic: bool = True
    composition_depth: int = 0

class ReasoningConfig(BaseModel):
    task_type: str = "text_generation"
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
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

class ContextPolicy(BaseModel):
    """Context filtering policy for step execution."""
    type: str = "FULL"  # FULL | LAST_N | SLIDING_WINDOW | EXPLICIT
    n: Optional[int] = None  # For LAST_N: number of previous steps to include
    max_chars: Optional[int] = None  # For SLIDING_WINDOW: max characters
    summarize_threshold: Optional[int] = 8000  # Auto-summarize if context exceeds this
    explicit_keys: List[str] = []  # For EXPLICIT: specific context keys to include
    # P2.6: Domain-specific keys to always preserve verbatim during summarization.
    # Replaces hardcoded ["age_group", "style", "topic"] that were baked into worker.py.
    preserve_keys: List[str] = []  # e.g. ["customer_name", "product_id", "language"]


class LogicGate(BaseModel):
    reasoning_config: ReasoningConfig
    retry_policy: RetryPolicy = RetryPolicy()
    review_mechanism: ReviewMechanism = ReviewMechanism()
    context_policy: ContextPolicy = ContextPolicy()  # Context filtering configuration

class ExitCondition(BaseModel):
    condition: str
    next_step: Any # Integer | 'END' | 'ESCALATE'

class PlanStepTarget(BaseModel):
    entity_id: Optional[UUID] = None
    tool_id: Optional[str] = None
    prompt_template: Optional[str] = None
    input_dependencies: List[str] = []  # Explicit step output dependencies (e.g., ["step_1", "step_2"])

class PlanStep(BaseModel):
    step_id: Optional[str] = None  # Accept string IDs from frontend
    order: int = 0
    name: str = ""
    description: Optional[str] = None
    type: Optional[str] = None  # Accept string type from frontend
    target: Optional[PlanStepTarget] = None
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
    name: Optional[str] = None
    description: Optional[str] = None
    provider: Optional[str] = None
    authentication: Optional[ToolAuth] = None
    function_schema: Optional[Dict[str, Any]] = None
    # P3.1 — Extended permission model (OpenCode-inspired)
    access_level: str = "READ"   # READ | WRITE | EXECUTE (legacy single-string, kept for compat)
    permissions: List[str] = []  # e.g. ["read", "write", "network", "storage", "execute"]
    sandbox_mode: bool = False
    max_execution_seconds: int = 30      # Per-call timeout enforcement
    rate_limit_per_run: Optional[int] = None  # Max calls per ExecutionRun (None = unlimited)


# Simple tool reference (just tool_id)
class ToolReference(BaseModel):
    tool_id: str

class CortexMemoryConfig(BaseModel):
    """Configuration for CORTEX cognitive tree memory mode."""
    max_children: int = 12           # MAX_CHILDREN invariant per node
    page_size_tokens: int = 8000     # Max tokens per content page
    context_budget_pct: int = 40     # % of context window for root run budget
    auto_checkpoint: bool = True     # Auto-checkpoint when budget exceeded
    resume_enabled: bool = True      # Enable resume from cursor

class MemoryConfig(BaseModel):
    """Memory configuration aligned with CORTEX memory system."""
    enabled: bool = False
    mode: str = "STANDARD"  # STANDARD | CORTEX
    # STANDARD mode: episodic + semantic memory
    episodic_memory_count: int = 10  # How many past episodes to inject
    semantic_search_enabled: bool = True  # pgvector document search
    semantic_top_k: int = 5
    # CORTEX mode: cognitive tree for unbounded context
    cortex_config: Optional[CortexMemoryConfig] = None

class ContextSourceType(str, Enum):
    DOCUMENT = "DOCUMENT"              # Design-time uploaded document
    KNOWLEDGE_BASE = "KNOWLEDGE_BASE"  # Existing tenant document collection
    CORTEX_TREE = "CORTEX_TREE"        # Previous CORTEX tree from any entity
    DB_RECORDS = "DB_RECORDS"          # Database records query

class ContextSource(BaseModel):
    """A design-time or runtime context source attached to an entity."""
    source_type: ContextSourceType
    reference_id: Optional[str] = None   # Document ID, tree ID, etc.
    query: Optional[str] = None          # For KB/DB: semantic search query
    description: Optional[str] = None    # Human-readable label
    ingest_to_cortex: bool = True        # Auto-ingest into CORTEX tree

class ContextEngineering(BaseModel):
    """Context engineering configuration — CORTEX-native."""
    context_sources: List[ContextSource] = []   # Design-time context attachments
    inject_episodic_memory: bool = True          # Include recent interaction history
    inject_semantic_context: bool = True         # Include relevant doc chunks
    inject_cortex_viewport: bool = True          # Include CORTEX tree viewport
    no_truncation: bool = True                   # CORTEX handles unbounded contexts

class Capabilities(BaseModel):
    tools: List[ToolReference] = []  # Accept simple tool references
    memory: MemoryConfig = MemoryConfig()
    context_engineering: ContextEngineering = ContextEngineering()

class ExecutionLimits(BaseModel):
    max_recursion_depth: int = 5
    max_tool_calls: Optional[int] = None

class Governance(BaseModel):
    max_cost_usd: Optional[float] = None
    timeout_ms: int = 60000
    max_recursion_depth: int = 5
    execution_limits: Optional[ExecutionLimits] = None
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
    goal: Optional[str] = None  # Used in prompt generation as the entity's objective
    type: EntityType
    version: str = "1.0.0"
    status: EntityStatus = EntityStatus.ACTIVE
    tags: List[str] = []
    
    identity: Optional[Any] = None  # Accept Persona or {persona: Persona} format
    hierarchy: Optional[Hierarchy] = None
    logic_gate: Optional[LogicGate] = None
    planning: Optional[Planning] = None
    capabilities: Optional[Capabilities] = None
    governance: Optional[Governance] = None
    io_contract: Optional[IOContract] = None
    observability: Optional[Observability] = None
    metadata_extensions: Optional[Dict[str, Any]] = None

    # Template fields
    is_template: bool = False  # True = blueprint entity, not executable
    template_source_id: Optional[UUID] = None  # ID of template this was cloned from

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
    goal: Optional[str] = None
    type: Optional[EntityType] = None  # Added to allow type updates
    status: Optional[EntityStatus] = None
    version: Optional[str] = None
    tags: Optional[List[str]] = None  # Added to allow tags updates
    identity: Optional[Any] = None  # Accept Any format like create (Persona or {persona: Persona})
    hierarchy: Optional[Hierarchy] = None
    logic_gate: Optional[LogicGate] = None
    planning: Optional[Planning] = None
    capabilities: Optional[Capabilities] = None
    governance: Optional[Governance] = None
    io_contract: Optional[IOContract] = None
    observability: Optional[Observability] = None
    metadata_extensions: Optional[Dict[str, Any]] = None
    parent_id: Optional[UUID] = None
    is_template: Optional[bool] = None
    template_source_id: Optional[UUID] = None
    is_active: Optional[bool] = None  # Added for legacy field support

class HierarchicalEntityResponse(HierarchicalEntityBase):
    id: UUID
    company_id: UUID
    parent_id: Optional[UUID]
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @field_validator("identity", mode="before")
    @classmethod
    def parse_identity(cls, v):
        if isinstance(v, dict) and "persona" in v:
            return v["persona"]
        return v
    
    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        if v is None:
            return []
        return v

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
    output_result: Optional[Any] = None
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

    @field_validator("total_cost_usd", mode="before")
    @classmethod
    def parse_total_cost_usd(cls, v):
        if v is None:
            return 0.0
        return v

    @field_validator("total_tokens", mode="before")
    @classmethod
    def parse_total_tokens(cls, v):
        if v is None:
            return 0
        return v

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


# ---------------------------------------------------------------------------
# CORTEX Memory Architecture Schemas
# ---------------------------------------------------------------------------

class CortexTreeStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    COMPLETE = "complete"
    ARCHIVED = "archived"

class CortexNodeType(str, Enum):
    ROOT = "root"
    KNOWLEDGE = "knowledge"
    FINDING = "finding"
    TASK = "task"
    OUTPUT = "output"
    CHECKPOINT = "checkpoint"

class CortexTreeCreate(BaseModel):
    entity_id: UUID
    task_description: str
    max_children: int = 12
    page_size_tokens: int = 8000
    context_budget_pct: int = 40

class CortexTreeResponse(BaseModel):
    id: UUID
    entity_id: UUID
    task_description: Optional[str]
    status: str
    total_nodes: int = 0
    root_node_id: Optional[str] = None
    output_root_id: Optional[str] = None
    resume_cursor_id: Optional[str] = None
    max_children: int = 12
    created_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class CortexTreeListResponse(BaseModel):
    id: UUID
    entity_id: UUID
    task_description: Optional[str]
    status: str
    total_nodes: int = 0
    created_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None

class CortexNodeSummary(BaseModel):
    id: str
    title: str
    summary: Optional[str]
    status: str
    node_type: str
    sibling_order: int = 0
    depth: int = 0
    content_tokens: int = 0

class CortexViewportResponse(BaseModel):
    current_node: CortexNodeSummary
    children: List[CortexNodeSummary]
    parent: Optional[CortexNodeSummary] = None
    breadcrumb: List[Dict[str, str]]

class CortexNodeContentResponse(BaseModel):
    node_id: str
    title: str
    content: str
    page: int
    total_pages: int
    content_tokens: int

class CortexNodeCreate(BaseModel):
    parent_id: UUID
    node_type: CortexNodeType
    title: str
    content: Optional[str] = None
    summary: Optional[str] = None
    status: str = "complete"
    source_ref: Optional[Dict[str, Any]] = None
    metadata_extra: Optional[Dict[str, Any]] = None

class CortexCheckpointCreate(BaseModel):
    progress_summary: str
    key_facts: List[str] = []
    next_steps: List[str] = []

class CortexRecurseRequest(BaseModel):
    node_id: UUID
    task: str
    result_slot: str

class CortexNodeDetailResponse(BaseModel):
    id: str
    tree_id: str
    parent_id: Optional[str] = None
    node_type: str
    title: str
    summary: Optional[str]
    content_tokens: int = 0
    status: str
    depth: int = 0
    sibling_order: int = 0
    source_ref: Optional[Dict[str, Any]] = None
    metadata_extra: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Tool Registry Management Schemas
# ---------------------------------------------------------------------------

class ToolRegistryEntryCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    function_schema: Optional[Dict[str, Any]] = None
    is_enabled: bool = True
    configuration: Optional[Dict[str, Any]] = None

class ToolRegistryEntryUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    function_schema: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    configuration: Optional[Dict[str, Any]] = None

class ToolRegistryEntryResponse(BaseModel):
    id: UUID
    company_id: Optional[UUID] = None
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tool_type: str = "BUILT_IN"
    function_schema: Optional[Dict[str, Any]] = None
    is_enabled: bool = True
    configuration: Optional[Dict[str, Any]] = None
    created_by: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
