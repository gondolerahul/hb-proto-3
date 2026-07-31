/**
 * The conversation seam (D6 §10, VG-07; R-4 part P).
 *
 * One turn in, one turn out. Both the Brainstorm's exchange and the Line's
 * thread speak to the same nine-stage runtime, so the endpoints live together
 * here rather than once per surface — the `fetchTrays`/`fetchTrayList` split
 * this round deletes is what two clients on one path becomes.
 *
 * **`needs_step_up` and `needs_oob` are read, never re-derived.** The turn
 * payload carries them precisely so the console opens the right ceremony
 * without the client re-computing a tier it does not own (the backend's own
 * note on `_turn_payload`). `awaiting_confirmation` is surfaced for the same
 * reason: stages 2 and 5 advance only on an explicit owner act, and the client
 * has to be *told* a confirmation is due rather than inferring it from a stage
 * number.
 *
 * There is a `POST /ai/pragya/chat/stream` beside this one that delivers the
 * same turn as SSE. It is deliberately not wrapped: it chunks a reply that was
 * already resolved in full, so it buys typing-animation and nothing else, and
 * it would be a second authorisation path to keep honest.
 */
import { api } from "./client";

export interface PragyaTurn {
  reply: string;
  stage: number;
  stage_name: string;
  auth_level: string;
  tier: string | null;
  /** True when a tool raised a HITL card this turn — the tray grew by one. */
  raised_approval: boolean;
  needs_step_up: boolean;
  needs_oob: boolean;
  command_ref: string | null;
  command_summary: string | null;
  cost_usd: number;
  awaiting_confirmation: boolean;
  advanced_to: number | null;
  artifacts_written: string[];
  reported_delegations: string[];
}

/** One turn of conversation. The Brainstorm's four beats are four of these. */
export async function sendTurn(message: string): Promise<PragyaTurn> {
  return (await api.post<PragyaTurn>("/ai/pragya/chat", { message })).data;
}

export interface PragyaHistoryTurn {
  role: string;
  content: string;
  at: string;
}

export async function fetchThreadHistory(): Promise<PragyaHistoryTurn[]> {
  return (await api.get<PragyaHistoryTurn[]>("/ai/pragya/history")).data;
}
