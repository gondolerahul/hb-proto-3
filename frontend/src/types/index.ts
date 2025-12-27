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

export interface LogicGate {
    reasoning_config: {
        model_provider: string;
        model_name: string;
        temperature: number;
        reasoning_mode: 'REACT' | 'CHAIN_OF_THOUGHT' | 'REFLECTION' | 'TREE_OF_THOUGHTS';
    };
    retry_policy: {
        max_retries: number;
        backoff_strategy: 'LINEAR' | 'EXPONENTIAL' | 'NONE';
    };
    review_mechanism: {
        enabled: boolean;
        review_prompt?: string;
    };
}

export interface Planning {
    static_plan: {
        enabled: boolean;
        steps: any[];
    };
    dynamic_planning: {
        enabled: boolean;
        planning_prompt?: string;
    };
    loop_control: {
        max_iterations: number;
    };
}

export interface capabilities {
    tools: any[];
    memory: {
        enabled: boolean;
        scope: string;
    };
    context_engineering: {
        max_context_tokens: number;
    };
}

export interface Governance {
    max_cost_usd?: number;
    timeout_ms: number;
    hitl_checkpoints: any[];
}

export interface IOContract {
    input_schema: any;
    output_schema: any;
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
    observability?: any;
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
