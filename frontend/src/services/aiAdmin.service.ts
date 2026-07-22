/**
 * Loop operations admin — the Inc-2 ONBOARD admin surfaces over the Inc-1 APIs:
 * signals inspector (/ai/signals), trigger registry (/ai/signals/triggers),
 * and the budget-envelope view (/ai/loop/envelope).
 */
import { apiClient } from './api.client';

export type SignalStatus = 'pending' | 'consumed' | 'parked' | 'escalated' | 'dead';

export interface SignalRow {
    id: string;
    source: string;
    type: string;
    urgency: string;
    confidence: number;
    trust: string;
    status: SignalStatus;
    object_refs: Record<string, unknown> | null;
    payload: Record<string, unknown> | null;
    dedupe_key: string | null;
    owner_process_id: string | null;
    consumed_by_run_id: string | null;
    park_review_at: string | null;
    attempts: number;
    replayed_from: string | null;
    last_error: string | null;
    created_at: string;
    consumed_at: string | null;
}

export interface SignalCoverage {
    counts: Partial<Record<SignalStatus, number>>;
    total: number;
    coverage_pct: number;
}

export interface TriggerRow {
    id: string;
    process_entity_id: string;
    type_pattern: string;
    priority: number;
    enabled: boolean;
    created_at: string;
}

export interface EnvelopeRow {
    id: string;
    entity_id: string;
    cycle: string;
    envelope_usd: number;
    reserved_usd: number;
    spent_usd: number;
    utilization_pct: number;
    downshift_at_pct: number;
    downshift: boolean;
    capped: boolean;
    refreshed_at: string | null;
}

export const aiAdminService = {
    // ── Signals inspector ──────────────────────────────────────────────
    getCoverage: async (): Promise<SignalCoverage> => {
        const res = await apiClient.get<SignalCoverage>('/ai/signals/coverage');
        return res.data;
    },

    listSignals: async (status?: SignalStatus, typePrefix?: string, limit = 50): Promise<SignalRow[]> => {
        const res = await apiClient.get<SignalRow[]>('/ai/signals', {
            params: {
                ...(status ? { status } : {}),
                ...(typePrefix ? { type_prefix: typePrefix } : {}),
                limit,
            },
        });
        return res.data;
    },

    replaySignal: async (signalId: string): Promise<{ id: string; replayed_from: string }> => {
        const res = await apiClient.post<{ id: string; replayed_from: string }>(
            `/ai/signals/${signalId}/replay`);
        return res.data;
    },

    // ── Trigger registry ───────────────────────────────────────────────
    listTriggers: async (): Promise<TriggerRow[]> => {
        const res = await apiClient.get<TriggerRow[]>('/ai/signals/triggers');
        return res.data;
    },

    updateTrigger: async (
        triggerId: string,
        patch: { priority?: number; enabled?: boolean },
    ): Promise<{ id: string; priority: number; enabled: boolean }> => {
        const res = await apiClient.patch<{ id: string; priority: number; enabled: boolean }>(
            `/ai/signals/triggers/${triggerId}`, patch);
        return res.data;
    },

    // ── Budget envelope ────────────────────────────────────────────────
    getEnvelopes: async (): Promise<EnvelopeRow[]> => {
        const res = await apiClient.get<EnvelopeRow[]>('/ai/loop/envelope');
        return res.data;
    },
};
