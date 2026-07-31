/**
 * The Undercroft's bays (D6 §15; R-4 part P) — the engine room's reads.
 *
 * The Undercroft asserts in prose that each named endpoint *answers today*,
 * which makes a wrong path on that surface a false statement on the one
 * surface whose whole job is to be checkable. Three of the fixture's `source`
 * strings are wrong and one named an endpoint that did not exist; the
 * corrected paths are the ones this module calls, and each is annotated with
 * what the fixture said instead so the correction is auditable from here.
 *
 * Six bays are wrapped: signals, triggers, envelopes, routing, consent, flags.
 * The other three already had wrappers — the manifest bay reads
 * `readManifestLog()` (in-memory, no endpoint), traces read `fetchExecutions`,
 * and the schema browser reads `fetchDefs`.
 */
import { api } from "./client";

/* ─────────────────────────────────────────────────────────────── the bus */

/** A signal as the bus serves it. `park_review_at` and `consumed_at` are the
 * two absences that matter: a signal in flight has neither, and neither is
 * ever rendered as a time that has not happened. */
export interface SignalOut {
  id: string;
  source: string;
  type: string;
  urgency: string | null;
  confidence: number | null;
  trust: string | null;
  status: string;
  object_refs: unknown;
  payload: Record<string, unknown> | null;
  dedupe_key: string | null;
  owner_process_id: string | null;
  consumed_by_run_id: string | null;
  park_review_at: string | null;
  attempts: number;
  replayed_from: string | null;
  last_error: string | null;
  created_at: string;
  consumed_at: string | null;
}

/** `GET /ai/signals` — the fixture had this one right. The server caps `limit`
 * at 200 however large a number is asked for, so a caller must not read a
 * short list as "that is all there is". */
export async function fetchSignals(options?: {
  status?: string;
  typePrefix?: string;
  limit?: number;
}): Promise<SignalOut[]> {
  const params: Record<string, string | number> = {
    limit: options?.limit ?? 50,
  };
  if (options?.status !== undefined) params["status"] = options.status;
  if (options?.typePrefix !== undefined) params["type_prefix"] = options.typePrefix;
  return (await api.get<SignalOut[]>("/ai/signals", { params })).data;
}

export interface TriggerRegistration {
  id: string;
  process_entity_id: string;
  type_pattern: string;
  priority: number;
  enabled: boolean;
  created_at: string;
}

/** `GET /ai/signals/triggers` — what fires what. */
export async function fetchTriggers(): Promise<TriggerRegistration[]> {
  return (await api.get<TriggerRegistration[]>("/ai/signals/triggers")).data;
}

/* ─────────────────────────────────────────────────────────────── envelopes */

/**
 * A budget envelope, with the protected reserve **as an amount**.
 *
 * This is the join the district room needs: the estate projection reports only
 * `reserve_protected: boolean` on a district's treasury, so the gauge's gold
 * reserve seam has no width to draw from there. `reserved_usd` is here, and
 * the estate block carries `envelope_id`, so the two join on that id. Until a
 * caller makes that join the seam states a fact and does not draw to scale —
 * which is correct under the never-invent-a-number rule, and is a gap rather
 * than a design.
 */
export interface BudgetEnvelopeOut {
  id: string;
  entity_id: string;
  cycle: string;
  envelope_usd: number;
  reserved_usd: number;
  spent_usd: number;
  utilization_pct: number;
  downshift_at_pct: number;
  downshift: boolean;
  capped: boolean;
  refreshed_at: string | null;
}

/** `GET /ai/loop/envelope` — budget, spend, holds, reserve. */
export async function fetchEnvelopes(): Promise<BudgetEnvelopeOut[]> {
  return (await api.get<BudgetEnvelopeOut[]>("/ai/loop/envelope")).data;
}

/* ───────────────────────────────────────────────────────────────── routing */

/**
 * One routing decision: which model, why, and whether the fallback carried it.
 *
 * **Cost is not on this row.** The fixture's routing table carries a per-run
 * `costINR`; `RoutingDecision` stores no cost at all, and cost attribution
 * lives against the run. So the bay can say which model and why, and it must
 * not say what it cost until that join exists (gap in the report).
 */
export interface RoutingDecisionOut {
  id: string;
  run_id: string | null;
  task_type: string | null;
  model_registry_id: string | null;
  reason: string | null;
  fallback_used: boolean;
  signals: Record<string, unknown> | null;
  created_at: string | null;
}

/**
 * `GET /ai/intelligence/routing-decisions`.
 *
 * The fixture says `/ai/intelligence/routing`, which 404s. The server clamps
 * `limit` to 1–500.
 */
export async function fetchRoutingDecisions(
  limit = 100,
): Promise<RoutingDecisionOut[]> {
  return (
    await api.get<RoutingDecisionOut[]>("/ai/intelligence/routing-decisions", {
      params: { limit },
    })
  ).data;
}

/* ───────────────────────────────────────────────────────────────── consent */

/**
 * A channel's posture, in the registry's own words.
 *
 * `purposes` is per-purpose and reports only `marketing` and `transactional`:
 * `recording` is deliberately absent because nothing sets it yet, and
 * publishing "open" for a purpose no tenant was ever asked about would be a
 * claim the registry cannot support. `reason` is the *restricting* reason
 * where one restricts — never "no posture set" beside a closed gate.
 */
export interface ConsentChannel {
  channel: string;
  posture: "open" | "restricted" | "closed";
  reason: string;
  purposes: Record<string, boolean>;
  dnc: number;
  unsubscribed: number;
  granted: number;
  denied: number;
}

/** One row in the consent bay. `kind` says which of the three tables it came
 * from, and the fields the other two do not have are `null` rather than
 * flattened away — a DNC entry has no purpose and no status, and saying so is
 * cheaper than a reader guessing. */
export interface ConsentEntry {
  kind: "dnc" | "unsubscribe" | "consent";
  channel: string;
  identity: string;
  purpose: string | null;
  status: string | null;
  reason: string | null;
  at: string | null;
}

export interface ConsentView {
  as_of: string;
  totals: { dnc: number; unsubscribed: number; granted: number; denied: number };
  channels: ConsentChannel[];
  entries: ConsentEntry[];
  limit: number;
}

/**
 * `GET /ai/consent` — who asked us to stop.
 *
 * The fixture names this path and until very recently it was the one that had
 * **never existed**: the tables, the registry and migration `trust001` all
 * shipped behind no router. D8's E1 built the door, and the path the fixture
 * guessed turned out to be the path that was built, so this is the one of the
 * four wrong strings that fixed itself.
 *
 * Read-only by design. Writing consent is an act with a counterparty on the
 * other end of it, so it belongs to the flows that have the counterparty's
 * word — never to a panel that lists them.
 */
export async function fetchConsent(limit = 200): Promise<ConsentView> {
  return (await api.get<ConsentView>("/ai/consent", { params: { limit } })).data;
}

/* ─────────────────────────────────────────────────────────────────── flags */

/**
 * The resolved flag picture: platform defaults, numeric defaults, and the
 * overrides that beat them.
 *
 * An override is keyed by scope, so `{"company": true}` and `{"global": true}`
 * are different statements — which is exactly what the bay's "for whom" column
 * shows, and why this is not flattened to a single boolean here.
 */
export interface FeatureFlagView {
  defaults: Record<string, boolean>;
  numeric_defaults: Record<string, number>;
  overrides: Record<string, { company?: boolean; global?: boolean }>;
}

/**
 * `GET /ai/admin/feature_flags/me`.
 *
 * The fixture says `/ai/flags`, which does not exist. The real path is under
 * `/ai/admin`, but the endpoint is not admin-only — it answers for the calling
 * session and is what `useFeatureFlag(key)` reads. The `/admin` prefix is where
 * the router was mounted, not a statement about who may call it.
 */
export async function fetchFeatureFlags(): Promise<FeatureFlagView> {
  return (await api.get<FeatureFlagView>("/ai/admin/feature_flags/me")).data;
}

/**
 * Is a flag on for this session — defaults, then global override, then company
 * override, last one wins. Returns `null` when the registry has never heard of
 * the key, because "off" and "unknown" are different answers and the bay shows
 * them differently.
 */
export function flagState(
  view: FeatureFlagView,
  key: string,
): { on: boolean; scope: "default" | "global" | "company" } | null {
  const override = view.overrides[key];
  if (override?.company !== undefined) {
    return { on: override.company, scope: "company" };
  }
  if (override?.global !== undefined) {
    return { on: override.global, scope: "global" };
  }
  const fallback = view.defaults[key];
  if (fallback === undefined) return null;
  return { on: fallback, scope: "default" };
}
