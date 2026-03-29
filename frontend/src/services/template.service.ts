/**
 * template.service.ts — Agent Template API Service
 *
 * CRUD + Clone operations for agent templates (hierarchical entities with is_template=true).
 */
import { apiClient } from './api.client';
import { HierarchicalEntity } from '@/types';

export const templateService = {
    async listTemplates(type?: string): Promise<HierarchicalEntity[]> {
        const params = type ? `?type=${type}` : '';
        const { data } = await apiClient.get(`/ai/templates${params}`);
        return data;
    },

    async getTemplate(templateId: string): Promise<HierarchicalEntity> {
        const { data } = await apiClient.get(`/ai/templates/${templateId}`);
        return data;
    },

    async createTemplate(templateData: any): Promise<HierarchicalEntity> {
        const { data } = await apiClient.post('/ai/templates', templateData);
        return data;
    },

    async updateTemplate(templateId: string, templateData: any): Promise<HierarchicalEntity> {
        const { data } = await apiClient.put(`/ai/templates/${templateId}`, templateData);
        return data;
    },

    async deleteTemplate(templateId: string): Promise<void> {
        await apiClient.delete(`/ai/templates/${templateId}`);
    },

    async cloneTemplate(templateId: string): Promise<HierarchicalEntity> {
        const { data } = await apiClient.post(`/ai/templates/${templateId}/clone`);
        return data;
    },
};
