export interface Company {
    id: string;
    name: string;
    type: 'APP' | 'PARTNER' | 'TENANT';
    parent_id?: string;
    logo_url?: string;
    status: 'active' | 'suspended';
    created_at: string;
    updated_at: string;
}

export interface User {
    id: string;
    email: string;
    full_name: string;
    role: UserRole;
    company_id: string;
    profile_picture_url?: string;
    is_active: boolean;
    created_at: string;
}

export enum UserRole {
    APP_ADMIN = 'app_admin',
    PARTNER_ADMIN = 'partner_admin',
    TENANT_ADMIN = 'tenant_admin',
    APP_USER = 'app_user',
    PARTNER_USER = 'partner_user',
    TENANT_USER = 'tenant_user',
}

export interface LoginRequest {
    email: string;
    password: string;
}

export interface RegisterRequest {
    email: string;
    password: string;
    full_name: string;
}

export interface AuthResponse {
    access_token: string;
    refresh_token: string;
    token_type: string;
    user: User;
}

export interface ModelConfig {
    provider: string;
    model: string;
    temperature: number;
    max_tokens?: number;
    tools: string[];
}

export enum EntityType {
    ACTION = 'ACTION',
    SKILL = 'SKILL',
    AGENT = 'AGENT',
    PROCESS = 'PROCESS',
}

export enum EntityStatus {
    DRAFT = 'DRAFT',
    ACTIVE = 'ACTIVE',
    DEPRECATED = 'DEPRECATED',
    ARCHIVED = 'ARCHIVED',
}

export enum RunStatus {
    PENDING = 'PENDING',
    RUNNING = 'RUNNING',
    COMPLETED = 'COMPLETED',
    FAILED = 'FAILED',
    REPAIRING = 'REPAIRING',
}

// Nested Entity Interfaces

export interface PersonaExample {
    scenario: string;
    ideal_response: string;
}

export interface Persona {
    system_prompt: string;
    examples: PersonaExample[];
    behavioral_constraints: string[];
    few_shot_examples?: { [key: string]: string }[]; // New strict few-shot examples
}

export interface HierarchyChild {
    child_id: string;
    child_type: EntityType;
    relationship: 'SEQUENTIAL' | 'PARALLEL' | 'CONDITIONAL';
    condition?: {
        enabled: boolean;
        expression?: string;
        description?: string;
    };
}

export interface Hierarchy {
    parent_id?: string;
    children: HierarchyChild[];
    is_atomic: boolean;
    composition_depth: number;
}

export interface ContextPolicy {
    type: 'FULL' | 'LAST_N' | 'SLIDING_WINDOW' | 'EXPLICIT';
    n?: number;
    max_chars?: number;
    summarize_threshold?: number;
    explicit_keys?: string[];
}

export interface LogicGate {
    reasoning_config: {
        model_provider: string;
        model_name: string;
        temperature: number;
        top_p?: number;
        max_tokens?: number;
        reasoning_mode: 'REACT' | 'CHAIN_OF_THOUGHT' | 'REFLECTION' | 'TREE_OF_THOUGHTS';
    };
    retry_policy: {
        max_retries: number;
        backoff_strategy: 'LINEAR' | 'EXPONENTIAL' | 'NONE';
        backoff_multiplier?: number;
        retry_on?: string[];
    };
    review_mechanism: {
        enabled: boolean;
        review_prompt?: string;
        on_failure?: 'RETRY' | 'ESCALATE' | 'ABORT';
        success_criteria?: any[];
    };
    context_policy?: ContextPolicy;
}

export interface PlanStepTarget {
    entity_id?: string;
    tool_id?: string;
    prompt_template?: string;
    input_dependencies?: string[]; // Explicit dependencies
}

export interface PlanStep {
    step_id: string;
    order: number;
    name: string;
    description?: string;
    type: 'ACTION' | 'TOOL_CALL' | 'CHILD_ENTITY_INVOCATION' | 'THOUGHT';
    target?: PlanStepTarget;
    required: boolean;
    exit_conditions?: any[];
}

export interface Planning {
    static_plan: {
        enabled: boolean;
        steps: PlanStep[];
        fallback_behavior?: 'STRICT' | 'ADAPTIVE' | 'DYNAMIC_ONLY';
    };
    dynamic_planning: {
        enabled: boolean;
        planning_prompt?: string;
        constraints?: string[];
        reconciliation_strategy?: 'STATIC_PRIORITY' | 'DYNAMIC_PRIORITY' | 'HYBRID';
        allowed_deviations?: {
            can_add_steps: boolean;
            can_skip_optional_steps: boolean;
            can_reorder_steps: boolean;
            can_change_tools: boolean;
        };
    };
    loop_control: {
        max_iterations: number;
        iteration_context_mode?: 'FULL_HISTORY' | 'SUMMARIZED' | 'LAST_N';
    };
}

export interface capabilities {
    tools: any[];
    memory: {
        enabled: boolean;
        scope: string;
        storage_backend?: string;
    };
    context_engineering: {
        max_context_tokens: number;
        context_priority?: string[];
        artifact_handling?: {
            artifact_reference_mode: 'INLINE' | 'REFERENCE' | 'SUMMARY';
            store_large_objects: boolean;
        };
    };
}

export interface Governance {
    max_cost_usd?: number;
    timeout_ms: number;
    execution_limits?: {
        max_recursion_depth: number;
        max_tool_calls?: number;
    };
    hitl_checkpoints: any[];
}

export interface IOContract {
    input_schema: any;
    output_schema: any;
}

export interface Observability {
    log_level: string;
    log_thoughts: boolean;
    track_cost: boolean;
}

export interface HierarchicalEntity {
    id: string;
    company_id: string;
    parent_id?: string;
    name: string;
    display_name?: string;
    description?: string;
    type: EntityType;
    version: string;
    status: EntityStatus;
    tags: string[];

    identity?: Persona;
    hierarchy?: Hierarchy;
    logic_gate?: LogicGate;
    planning?: Planning;
    capabilities?: capabilities;
    governance?: Governance;
    io_contract?: IOContract;
    observability?: Observability;
    metadata_extensions?: any;

    created_at: string;
    updated_at: string;
}

export interface LLMInteractionLog {
    id: string;
    run_id: string;
    model_provider: string;
    model_name: string;
    input_prompt: string;
    output_response: string;
    prompt_tokens: number;
    completion_tokens: number;
    latency_ms?: number;
    cost_usd: number;
    reasoning_mode?: string;
    created_at: string;
}

export interface ToolInteractionLog {
    id: string;
    run_id: string;
    tool_id: string;
    tool_name: string;
    success: boolean;
    latency_ms?: number;
    created_at: string;
}

export interface HumanApproval {
    id: string;
    run_id: string;
    checkpoint_trigger: string;
    status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'TIMEOUT';
    requested_at: string;
    responded_at?: string;
}

export interface ExecutionRun {
    id: string;
    entity_id: string;
    parent_run_id?: string;
    company_id: string;
    status: RunStatus;
    input_data?: any;
    dynamic_plan?: any;
    result_data?: any;
    context_state?: any;
    error_message?: string;

    total_cost_usd: number;
    total_tokens: number;
    execution_time_ms?: number;
    trace_id?: string;

    started_at?: string;
    completed_at?: string;
    created_at: string;

    llm_logs?: LLMInteractionLog[];
    tool_logs?: ToolInteractionLog[];
    human_approvals?: HumanApproval[];
    child_runs?: ExecutionRun[];
    entity?: HierarchicalEntity;
}
