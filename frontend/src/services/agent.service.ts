/**
 * services/agent.service.ts — Phase 11 agent-level admin endpoints.
 *
 * Thin typed wrappers around /api/v1/ai/phase11/* routes.
 */
import { apiClient } from './api.client';
import type {
    AgentStateSnapshot,
    BanditTable,
    CostAttributionRow,
    HealthRecordRow,
    PlanCandidatesResponse,
    TraceSpan,
} from '@/types/phase11';

export const agentService = {
    async getAgentState(runId: string): Promise<AgentStateSnapshot | null> {
        const { data } = await apiClient.get(
            `/ai/executions/${runId}/agent_state`,
        );
        // The endpoint wraps the payload as { run_id, snapshot_at, snapshot }.
        // Unwrap to the AgentStateSnapshot the panel renders.
        const snap = (data && data.snapshot) ? data.snapshot : data;
        return snap ?? null;
    },

    async getHealthRecords(runId: string): Promise<HealthRecordRow[]> {
        const { data } = await apiClient.get(
            `/ai/phase11/executions/${runId}/health_records`,
        );
        return Array.isArray(data) ? data : [];
    },

    /**
     * Full execution trace (steps → child invocations → tool calls → LLM
     * calls). Backfills the per-iteration span tree for finished runs; merged
     * with the live SSE span stream in P11AgentLoopExecutionDetail.
     */
    async getTrace(runId: string): Promise<TraceSpan[]> {
        const { data } = await apiClient.get(
            `/ai/executions/${runId}/trace`,
        );
        return Array.isArray(data?.spans) ? data.spans : [];
    },

    async getPlanCandidates(runId: string): Promise<PlanCandidatesResponse> {
        const { data } = await apiClient.get(
            `/ai/phase11/executions/${runId}/plan_candidates`,
        );
        return data ?? { chosen: null, alternates: [], judge_reasoning: '' };
    },

    async getRunCostAttribution(runId: string): Promise<CostAttributionRow[]> {
        const { data } = await apiClient.get(
            `/ai/phase11/executions/${runId}/cost_attribution`,
        );
        return Array.isArray(data) ? data : [];
    },

    async getBanditState(
        entityId: string,
        taskClass = 'general',
    ): Promise<BanditTable> {
        const { data } = await apiClient.get(
            `/ai/phase11/entities/${entityId}/bandit_state`,
            { params: { task_class: taskClass } },
        );
        return data ?? { entity_id: entityId, task_class: taskClass, arms: {} };
    },
};
