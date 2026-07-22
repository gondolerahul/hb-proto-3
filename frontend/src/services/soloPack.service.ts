/**
 * Solo Pack onboarding — the Inc-2 ONBOARD wizard step APIs.
 *
 * These four calls are the backend contract of the setup wizard
 * (docs/product-road-map/increment-2/04_onboard_wizard.md). They are authored
 * as Pragya's Inc-3 stage APIs, so the conversational flow later drives the
 * exact same endpoints.
 */
import { apiClient } from './api.client';

export interface SoloPackBundle {
    key: string;
    display_name: string;
    is_default: boolean;
    /** false for bundles whose §2.1 processes have no Wave-0 template yet */
    available_now: boolean;
    /** the Wave-0 processes that would actually activate now */
    process_codes: string[];
    /** full §2.1 membership (only present on starter bundles) */
    all_processes?: string[];
    agent_count: number;
}

export interface GovernanceEntitySummary {
    name: string;
    display_name: string | null;
    code: string | null;
    type: string;
    autonomy_level: string | null;
    authority: Record<string, unknown> | null;
    checkpoint_keys: string[];
    sod_class: string;
    memory_domains: string[];
}

export interface GovernancePreview {
    bundle: string;
    autonomy_note: string;
    gateways: GovernanceEntitySummary[];
    processes: {
        process: GovernanceEntitySummary;
        agents: GovernanceEntitySummary[];
    }[];
}

export interface ActivationResponse {
    activated: boolean;
    bundle: string;
    /** name → entity_id for everything seeded (existing entities included) */
    entities: Record<string, string>;
}

export interface SoloPackStatus {
    activated: boolean;
    entity_count: number;
    entities: string[];
    trigger_count: number;
    /** where PolicyGate HITL cards land */
    console_path: string;
}

export const soloPackService = {
    listBundles: async (): Promise<SoloPackBundle[]> => {
        const res = await apiClient.get<SoloPackBundle[]>('/ai/onboarding/bundles');
        return res.data;
    },

    governancePreview: async (bundleKey: string): Promise<GovernancePreview> => {
        const res = await apiClient.get<GovernancePreview>('/ai/onboarding/governance-preview', {
            params: { bundle: bundleKey },
        });
        return res.data;
    },

    activate: async (bundleKey: string): Promise<ActivationResponse> => {
        const res = await apiClient.post<ActivationResponse>('/ai/onboarding/activate', {
            bundle_key: bundleKey,
        });
        return res.data;
    },

    getStatus: async (): Promise<SoloPackStatus> => {
        const res = await apiClient.get<SoloPackStatus>('/ai/onboarding/status');
        return res.data;
    },
};
