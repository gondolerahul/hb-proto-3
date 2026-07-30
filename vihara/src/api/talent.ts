/**
 * Talent clients (DRIVER D7, D6 §9) — candidates from the template
 * marketplace, hires as entity creation (landing at A1 — raising a band
 * later is the certified act, hiring at the floor is not), and VG-18's
 * termination endpoint with its honest 409 refusal.
 */
import { api } from "./client";
import type { EntityOut } from "./entities";

export async function fetchTemplates(): Promise<EntityOut[]> {
  return (await api.get<EntityOut[]>("/ai/templates")).data;
}

export async function fetchEntities(): Promise<EntityOut[]> {
  return (await api.get<EntityOut[]>("/ai/entities")).data;
}

/** Hire = clone the template into a live AGENT under a process, at A1.
 * The band is forced here so a template authored at A3 cannot smuggle
 * its band past the certified autonomy-change act. */
export async function hireFromTemplate(
  template: EntityOut,
  processId: string,
  name: string,
): Promise<EntityOut> {
  const governance =
    template.governance !== null && typeof template.governance === "object"
      ? { ...template.governance }
      : {};
  governance["autonomy_level"] = "A1";
  const body = {
    name,
    display_name: name,
    description: template.description,
    goal: (template as { goal?: string | null }).goal ?? null,
    type: "AGENT",
    identity: (template as { identity?: unknown }).identity ?? null,
    capabilities: (template as { capabilities?: unknown }).capabilities ?? null,
    io_contract: (template as { io_contract?: unknown }).io_contract ?? null,
    governance,
    hierarchy: { parent_id: processId, children: [], is_atomic: true, composition_depth: 0 },
    is_template: false,
    template_source_id: template.id,
  };
  return (await api.post<EntityOut>("/ai/entities", body)).data;
}

export interface TerminationRefusal {
  error: "termination_refused";
  reason: string;
  running_run_ids: string[];
}

export interface TerminationDone {
  status: string;
  memo_artifact_id: string | null;
  summary: {
    name: string;
    runs_total: number;
    runs_completed: number;
    pending_approvals: number;
  };
}

export function parseTerminationRefusal(
  error: unknown,
): TerminationRefusal | null {
  const response = (
    error as { response?: { status?: number; data?: { detail?: unknown } } }
  ).response;
  if (response?.status !== 409) return null;
  const detail = response.data?.detail;
  if (detail === null || typeof detail !== "object") return null;
  if ((detail as { error?: unknown }).error !== "termination_refused") {
    return null;
  }
  return detail as TerminationRefusal;
}

export async function terminateColleague(
  entityId: string,
): Promise<TerminationDone> {
  return (
    await api.post<TerminationDone>(
      `/ai/talent/colleagues/${entityId}/terminate`,
    )
  ).data;
}
