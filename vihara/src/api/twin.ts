/**
 * The Glasshouse's reads and writes (GLASS X5).
 *
 * Note what is absent and must stay absent: nothing here sends a
 * `grade`. The grade is computed by the engine from what a run actually
 * had (TWIN §5.4), and the surest way to keep the honesty layer
 * unsoftenable is to give the client no way to speak about it.
 */
import { api } from "./client";

export interface Scenario {
  id: string;
  name: string;
  kind: string;
  scope: { objects?: string[]; window_days?: number };
  status: string;
  acknowledged_estimate_usd: number | null;
}

export interface TwinRunView {
  id: string;
  grade: string;
  grade_means: string;
  method: string | null;
  metrics: Record<string, unknown>;
  cost_usd: number;
  is_baseline: boolean;
  refusal_reason: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface ScenarioEstimate {
  estimate: { rows: number; signals: number; usd: number; method: string };
  budget: {
    admitted: boolean;
    parked: boolean;
    reason: string;
    spent_today_usd: number;
    daily_cap_usd: number;
  };
}

export async function fetchScenarios(): Promise<Scenario[]> {
  const { data } = await api.get<{ scenarios: Scenario[] }>("/ai/twin/scenarios");
  return data.scenarios;
}

export async function fetchRuns(scenarioId: string): Promise<TwinRunView[]> {
  const { data } = await api.get<{ runs: TwinRunView[] }>(
    `/ai/twin/scenarios/${scenarioId}/runs`,
  );
  return data.runs;
}

export async function estimateScenario(
  scenarioId: string,
): Promise<ScenarioEstimate> {
  const { data } = await api.post<ScenarioEstimate>(
    `/ai/twin/scenarios/${scenarioId}/estimate`,
    {},
  );
  return data;
}

export async function runScenario(scenarioId: string): Promise<void> {
  await api.post(`/ai/twin/scenarios/${scenarioId}/run`, {});
}

export async function createScenario(input: {
  name: string;
  kind?: string;
  levers?: Record<string, unknown>;
  scope?: { objects?: string[]; window_days?: number };
}): Promise<{ id: string }> {
  const { data } = await api.post<{ id: string }>("/ai/twin/scenarios", input);
  return data;
}

export async function promoteRun(
  runId: string,
  input: { entity_id: string; field: string; addition: string },
): Promise<{ approval_id: string }> {
  const { data } = await api.post<{ approval_id: string }>(
    `/ai/twin/runs/${runId}/promote`,
    input,
  );
  return data;
}
