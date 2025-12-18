import { apiClient } from './api.client';

export interface Tenant {
    id: string;
    name: string;
    status: 'active' | 'suspended';
    partner_id?: string;
    created_at: string;
}

export interface TenantUpdate {
    status?: 'active' | 'suspended';
    name?: string;
}

export const tenantService = {
    getTenants: async (): Promise<Tenant[]> => {
        const response = await apiClient.get<Tenant[]>('/tenants');
        return response.data;
    },

    updateTenant: async (id: string, data: TenantUpdate): Promise<Tenant> => {
        const response = await apiClient.put<Tenant>(`/tenants/${id}`, data);
        return response.data;
    }
};
