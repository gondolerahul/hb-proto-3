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

export interface Agent {
    id: string;
    company_id: string;
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
    company_id: string;
    name: string;
    description?: string;
    dag: any;
    created_at: string;
    updated_at: string;
}

export interface Execution {
    id: string;
    company_id: string;
    agent_id?: string;
    workflow_id?: string;
    status: 'queued' | 'running' | 'completed' | 'failed';
    input: any;
    output?: any;
    error?: string;
    created_at: string;
    completed_at?: string;
}
