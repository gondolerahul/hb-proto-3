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
    executed: boolean;
    needs_step_up: boolean;
    needs_oob: boolean;
    command_ref: string | null;
    command_summary: string | null;
    citations: Array<Record<string, unknown>>;
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

    getReport: async (): Promise<{ kpis: KpiReading[] }> => {
        const { data } = await apiClient.get('/ai/pragya/report');
        return data;
    },
};
