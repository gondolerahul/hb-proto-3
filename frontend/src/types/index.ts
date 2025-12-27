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

export enum RunStatus {
    PENDING = 'PENDING',
    RUNNING = 'RUNNING',
    COMPLETED = 'COMPLETED',
    FAILED = 'FAILED',
    REPAIRING = 'REPAIRING',
}

export interface HierarchicalEntity {
    id: string;
    company_id: string;
    parent_id?: string;
    name: string;
    description?: string;
    type: EntityType;
    static_plan?: any;
    llm_config?: ModelConfig;
    toolkit?: any[];
    is_active: boolean;
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
    created_at: string;
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
    started_at?: string;
    completed_at?: string;
    created_at: string;
    llm_logs?: LLMInteractionLog[];
    child_runs?: ExecutionRun[];
    entity?: HierarchicalEntity;
}
