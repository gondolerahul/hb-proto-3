/**
 * The tray client (DRIVER D1, D5 §4). The shapes mirror the composer in
 * `backend/src/ai/genui/trays.py` exactly — nullable where the composer
 * admits an honest absence (`recommendation`, `paths[].cost`, `currency`),
 * because rendering those absences honestly is a contract, not a fallback.
 */
import { api } from "./client";

export interface TrayCost {
  amount: number;
  currency: string | null;
  basis: string;
}

export interface TrayPath {
  key: string;
  label: string;
  consequence: string;
  cost: TrayCost | null;
}

export interface TrayRecommendation {
  sentence: string;
  why: string | null;
  honesty_grade?: string;
  twin_run_id?: string | null;
}

export interface TrayCertifiedBlock {
  component: string;
  tier: string;
  props: Record<string, unknown>;
  manifest_hash: string;
}

export interface Tray {
  tray_id: string;
  approval_id: string;
  checkpoint_key: string | null;
  what_happened: {
    sentence: string;
    object: { kind: string; id: string; label: string } | null;
  };
  recommendation: TrayRecommendation | null;
  paths: TrayPath[];
  certified: TrayCertifiedBlock;
  sla: { seconds_left: number | null; on_timeout: string | null };
  prepared_by: { entity_id: string; name: string } | null;
}

export async function fetchTrayList(): Promise<Tray[]> {
  return (await api.get<Tray[]>("/ai/genui/trays")).data;
}

export type TrayDecision = "APPROVED" | "REJECTED";

/**
 * The certified act itself. The endpoint is gated (`enforce_tier` in the
 * handler body) — a 403 `step_up_required` here is the ceremony asking,
 * and belongs to `useCertifiedAct`, not to this function.
 */
export async function respondToApproval(
  approvalId: string,
  status: TrayDecision,
  notes?: string,
): Promise<void> {
  await api.post(`/ai/approvals/${approvalId}/respond`, {
    status,
    ...(notes !== undefined ? { notes } : {}),
  });
}
