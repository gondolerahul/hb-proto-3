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

/** One composed tray. 404 on unknown *and* cross-tenant alike, so a caller
 * must not read it as "this tray was already answered". */
export async function fetchTray(trayId: string): Promise<Tray> {
  return (await api.get<Tray>(`/ai/genui/trays/${encodeURIComponent(trayId)}`)).data;
}

/* ────────────────────────────────────────── R-4 part P: the raw pending list */

/**
 * A pending approval as the governance console serves it
 * (`GET /ai/approvals/pending`).
 *
 * **This is not a tray and does not replace one.** `fetchTrayList` returns
 * spec §6.1's composed object — Pragya's sentence, the paths and their costs,
 * the certified block. This returns the approval row underneath it: the
 * checkpoint, the context snapshot, the SLA. Two views of one queue, and the
 * distinction is worth keeping because the tray is what a person answers while
 * this is what an operator audits.
 *
 * The reason a surface still needs it: `sla_seconds` here is the checkpoint's
 * *budget*, whereas a tray carries `sla.seconds_left`, the remainder. A
 * countdown needs both to draw a proportion, and neither endpoint has both.
 */
export interface PendingApproval {
  id: string;
  run_id: string;
  checkpoint_trigger: string | null;
  checkpoint_key: string | null;
  context_snapshot: Record<string, unknown>;
  status: string;
  requested_at: string;
  /** `null` when no checkpoint SLA governs this category — never zero. */
  sla_seconds: number | null;
  on_timeout: string | null;
}

export async function fetchPendingApprovals(): Promise<PendingApproval[]> {
  return (await api.get<PendingApproval[]>("/ai/approvals/pending")).data;
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
