/**
 * Strategy + KPI clients (DRIVER D6, D6 §8). Propositions and Minutes are
 * ordinary tenant records (the record API is their write path, on
 * purpose); what lives here is the one act the record API cannot do —
 * adoption, a T2 certified act spanning two records — and the KPI reads
 * the agenda composes from.
 */
import { api } from "./client";

export interface AdoptResult {
  resolution_id: string | null;
  proposition_id: string;
  status: string;
}

/** T2 certified — a plain session gets `step_up_required` here, and that
 * refusal belongs to `useCertifiedAct`. */
export async function adoptProposition(body: {
  proposition_id: string;
  title: string;
  decision: string;
  concerns_module?: string;
}): Promise<AdoptResult> {
  return (await api.post<AdoptResult>("/ai/strategy/adopt", body)).data;
}

export interface BusinessKpi {
  key: string;
  label?: string;
  value?: unknown;
  unit?: string | null;
  captured_today?: boolean;
  [key: string]: unknown;
}

export async function fetchBusinessKpis(): Promise<BusinessKpi[]> {
  const response = await api.get<BusinessKpi[] | { kpis?: BusinessKpi[] }>(
    "/ai/kpi/business",
  );
  const data = response.data;
  if (Array.isArray(data)) return data;
  return data.kpis ?? [];
}
