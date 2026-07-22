import { apiClient } from './api.client';

/**
 * Pragya — the account-manager console (Inc-3 PRAGYA).
 *
 * Every authorisation decision is the server's. This module carries the
 * server's answer (`needs_step_up`, `needs_oob`) to the UI so the right
 * ceremony opens, and never derives a tier itself — a second copy of the tier
 * table in the frontend is a second thing that can be wrong.
 */

export type Tier = 'T0' | 'T1' | 'T2' | 'T3';

export interface TurnResponse {
    reply: string;
    stage: number;
    stage_name: string;
    auth_level: string;
    tier: Tier | null;
    /** A tool raised a HITL card this turn; it settles at the Judgment Desk. */
    raised_approval: boolean;
    needs_step_up: boolean;
    needs_oob: boolean;
    command_ref: string | null;
    command_summary: string | null;
    cost_usd: number;
    /**
     * Stages 2 and 5 advance only on an explicit owner action, because their
     * deliverable IS the owner's agreement. The server tells us when one is
     * due — the console must not infer it from the stage number.
     */
    awaiting_confirmation: boolean;
    /** Set when the turn moved the engagement on by itself. */
    advanced_to: number | null;
    artifacts_written: string[];
    reported_delegations: string[];
}

export interface StageInfo {
    stage: number;
    name: string;
    summary: string;
    scripted: boolean;
}

export interface Engagement {
    stage: number;
    stage_name: string;
    stage_summary: string;
    scripted: boolean;
    artifact_keys: string[];
    history: Array<{ stage: number; at: string; reason: string }>;
    stages: StageInfo[];
}

export interface HistoryTurn {
    role: 'user' | 'pragya';
    content: string;
    stage: number;
    tier: Tier | null;
    outcome: string | null;
    at: string;
}

export interface KpiReading {
    key: string;
    display_name: string;
    unit: string;
    value: number | null;
    measurable: boolean;
    missing: string[];
    caveat: string | null;
}

export const pragyaService = {
    getEngagement: async (): Promise<Engagement> => {
        const { data } = await apiClient.get<Engagement>('/ai/pragya/engagement');
        return data;
    },

    getHistory: async (limit = 40): Promise<HistoryTurn[]> => {
        const { data } = await apiClient.get<HistoryTurn[]>(
            '/ai/pragya/history', { params: { limit } });
        return data;
    },

    send: async (message: string): Promise<TurnResponse> => {
        const { data } = await apiClient.post<TurnResponse>(
            '/ai/pragya/chat', { message });
        return data;
    },

    /**
     * Confirm the current stage — stages 2 and 5 only.
     *
     * Deliberately a distinct action rather than something inferred from the
     * conversation: these two stages exist because the owner's agreement is
     * the deliverable, and reading agreement out of "sounds about right" is
     * exactly what they guard against.
     */
    advance: async (): Promise<{ stage: number; stage_name: string }> => {
        const { data } = await apiClient.post('/ai/pragya/advance');
        return data;
    },

    getReport: async (): Promise<{ kpis: KpiReading[] }> => {
        const { data } = await apiClient.get('/ai/pragya/report');
        return data;
    },
};
