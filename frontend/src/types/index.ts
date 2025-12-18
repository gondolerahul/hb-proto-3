export interface User {
    id: string;
    email: string;
    full_name: string;
    role: UserRole;
    tenant_id: string;
    partner_id?: string;
    created_at: string;
}

export enum UserRole {
    APP_ADMIN = 'APP_ADMIN',
    PARTNER_ADMIN = 'PARTNER_ADMIN',
    TENANT_ADMIN = 'TENANT_ADMIN',
    TENANT_USER = 'TENANT_USER',
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

export interface Agent {
    id: string;
    tenant_id: string;
    name: string;
    description?: string;
    role: string;
    llm_config: ModelConfig;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

export interface Workflow {
    id: string;
    tenant_id: string;
    name: string;
    description?: string;
    dag: any;
    created_at: string;
    updated_at: string;
}

export interface Execution {
    id: string;
    tenant_id: string;
    agent_id?: string;
    workflow_id?: string;
    status: 'queued' | 'running' | 'completed' | 'failed';
    input: any;
    output?: any;
    error?: string;
    created_at: string;
    completed_at?: string;
}
