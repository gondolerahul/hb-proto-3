import { apiClient } from './api.client';

export interface BillingConfig {
    id: string;
    company_id: string | null;
    config_name: string;
    multiplier_factor: number;
    platform_fee_pct: number;
    sales_partner_fee_pct: number;
    discount_pct: number;
    is_active: boolean;
    updated_at: string;
}

export interface BillingEvent {
    id: string;
    company_id: string;
    period_month: string;
    grouping_type: string | null;
    grouping_value: string | null;
    base_cost: number;
    multiplied_cost: number;
    platform_fee_amount: number;
    partner_fee_amount: number;
    discount_amount: number;
    total_billing: number;
    telephony_in_minutes: number;
    telephony_out_minutes: number;
    image_gen_count: number;
    video_gen_count: number;
    other_ai_cost: number;
}

export interface ReportTotals {
    total_base_cost?: number;
    total_billing?: number;
    total_revenue?: number;
    total_telephony_in_minutes?: number;
    total_telephony_out_minutes?: number;
    total_image_gen?: number;
    total_video_gen?: number;
    total_other_ai_cost?: number;
    total_platform_fees?: number;
    total_partner_fees?: number;
    total_discounts?: number;
}

export interface ReportResponse {
    events: BillingEvent[];
    totals: ReportTotals;
    count: number;
}

export interface BillingConfigUpdate {
    multiplier_factor?: number;
    platform_fee_pct?: number;
    sales_partner_fee_pct?: number;
    discount_pct?: number;
    company_id?: string;
}

export const billingService = {
    getConfig: async (): Promise<{ config: BillingConfig | null }> => {
        const { data } = await apiClient.get('/billing/config');
        return data;
    },

    updateConfig: async (payload: BillingConfigUpdate): Promise<{ config: BillingConfig }> => {
        const { data } = await apiClient.put('/billing/config', payload);
        return data;
    },

    getCostingReport: async (params?: {
        period_month?: string;
        grouping_type?: string;
    }): Promise<ReportResponse> => {
        const qp = new URLSearchParams();
        if (params?.period_month) qp.append('period_month', params.period_month);
        if (params?.grouping_type) qp.append('grouping_type', params.grouping_type);
        const { data } = await apiClient.get<ReportResponse>(
            `/reports/costing?${qp.toString()}`
        );
        return data;
    },

    getBillingReport: async (params?: {
        period_month?: string;
        grouping_type?: string;
    }): Promise<ReportResponse> => {
        const qp = new URLSearchParams();
        if (params?.period_month) qp.append('period_month', params.period_month);
        if (params?.grouping_type) qp.append('grouping_type', params.grouping_type);
        const { data } = await apiClient.get<ReportResponse>(
            `/reports/billing?${qp.toString()}`
        );
        return data;
    },
};
