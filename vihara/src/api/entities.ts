/**
 * Entity + execution reads (DRIVER D4, D6 §5–6) — the dossier's bindings.
 * All shipped endpoints; shapes are read defensively because the legacy
 * response models carry more than the dossier needs.
 */
import { api } from "./client";

export interface EntityOut {
  id: string;
  name: string;
  display_name: string | null;
  type: string;
  description: string | null;
  governance: Record<string, unknown> | null;
  parent_id: string | null;
  [key: string]: unknown;
}

export interface RunSummary {
  id: string;
  entity_id: string;
  status: string;
  total_cost_usd: number;
  execution_time_ms: number | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export async function fetchEntity(entityId: string): Promise<EntityOut> {
  return (await api.get<EntityOut>(`/ai/entities/${entityId}`)).data;
}

/**
 * Every root execution this company has ever run.
 *
 * **Unbounded, and there is no filter.** `GET /ai/executions` takes no
 * parameters at all — no limit, no status, no district — and the service
 * orders the whole table newest-first. So the District room's live-runs panel
 * and the Undercroft's traces bay both have to read everything and narrow it
 * here, and on a tenant with real history that is the wrong shape of request.
 * Recorded rather than papered over: the fix is a paged, filterable execution
 * read on the backend, not a bigger client (gap R-4-P-3 in the build report).
 */
export async function fetchExecutions(): Promise<RunSummary[]> {
  return (await api.get<RunSummary[]>("/ai/executions")).data;
}

export async function fetchTrace(runId: string): Promise<unknown> {
  return (await api.get<unknown>(`/ai/executions/${runId}/trace`)).data;
}

/** The stable art key for a portrait: "agt-015-proposal-quote" → "agt-015". */
export function artKeyFor(entityName: string): string {
  const parts = entityName.toLowerCase().split("-");
  if (parts.length >= 2 && parts[0] === "agt") {
    return `${parts[0]}-${parts[1]}`;
  }
  return entityName.toLowerCase();
}
