/**
 * The colleague dossier (D8 E3; R-4 part W) — `GET /ai/entities/{id}/dossier`.
 *
 * **Why this file exists at all.** Part P wrapped thirteen regions and this was
 * not one of them, because the endpoint did not exist yet: E3 shipped after P
 * had already been measured, and its FastAPI signature returns a bare
 * `dict[str, Any]`, so `schema.d.ts` describes it as an object with no
 * properties. There is nothing to derive a type from. The shapes below are read
 * off `backend/src/ai/dossier/read.py` field by field, which is also why every
 * optional key here is optional for a stated reason rather than defensively.
 *
 * **`absent` is the point of the endpoint and therefore of this module.** The
 * read model ships a list naming, per field, what the platform cannot answer
 * and why — so a surface is *told* where to render an absence instead of
 * discovering an empty field and filling it in. `absenceOf` is how a region
 * asks. It returns the server's own sentence and nothing else: this module has
 * no fallback copy, because a client-side "not available" would quietly replace
 * seven specific, checkable reasons with one vague one.
 *
 * Two things the shapes deliberately do **not** have:
 *
 *  - **`reliability` carries no target and no dial fill.** `KpiDefinition`
 *    declares a baseline and no target, `HITLCheckpointDef.sla_seconds` is the
 *    human reviewer's deadline, and the demotion thresholds are the floor at
 *    which autonomy is *removed* rather than a level anyone promised. So there
 *    is no `target` field to bind a gauge to, and `demotion_bar` is named as
 *    what it is. `failure_rate` is `null` with no runs, never `0` — zero reads
 *    as "never fails".
 *  - **A competency's `note` is absent, not empty**, when the registry cannot
 *    resolve the tool. `registered: false` is the fact; a description invented
 *    for a tool that cannot be called would hide a live defect (the shipped
 *    templates grant `send_email`; the registered tool is `email_send`).
 */
import { api } from "./client";

/** One field the platform cannot answer, with the read model's own reason.
 *  `field` keys are stable — the surface keys regions off them. */
export interface DossierAbsence {
  field: string;
  why: string;
}

/** One term of engagement, and the column it was read from. Nothing is
 *  paraphrased into a voice the record does not have, so `source` is printed
 *  beside the clause rather than hidden in a tooltip. */
export interface CharterClause {
  label: string;
  value: string;
  source: string;
}

export interface DossierCompetency {
  name: string;
  kind: "tool" | "connector";
  /** Whether the platform can resolve the name at all. */
  registered: boolean;
  /** The §9.3 category the tool falls in, or `null` where it falls in none. */
  category: string | null;
  checkpoint_key: string | null;
  /** The registry's own description. **Omitted** when unregistered. */
  note?: string;
  /** The `mcp__<server>__<verb>` server segment, on connectors only. */
  connector_id?: string;
}

/**
 * What the gate says about one category, asked verbatim rather than recomputed.
 *
 * `conditional_on_amount` is the field that keeps this honest: the gate is
 * asked with **no amount**, because a dossier describes terms and not a
 * particular act, so a banded category that passes unamounted is autonomous
 * only *up to* `band`. A panel that flattened that to "autonomous" would be
 * true until the first large one.
 */
export interface DossierAuthority {
  category: string;
  tools: string[];
  checkpoint_key: string | null;
  /** `PASS` | `RAISE_HITL` | `BLOCK`, the gate's own vocabulary. */
  decision: string;
  reason: string;
  band: number | null;
  /** `"usd"` | `"pct"` | `"none"`. */
  unit: string;
  hard_block: number | null;
  always_hitl: boolean;
  conditional_on_amount: boolean;
  /** The four below come from the checkpoint registry row and are absent
   *  together when the platform has not seeded one. */
  checkpoint_description?: string;
  sla_seconds?: number | null;
  on_timeout?: string;
  platform_mandatory?: boolean;
}

/** The C4 threshold set — the point at which the sweep takes a level away.
 *  Deliberately not a target: a bar you fall through is not a level you aim
 *  for, which is why nothing here fills a dial. */
export interface DemotionBar {
  min_runs: number;
  failure_rate: number;
  latency_multiple: number;
  /** From `governance.timeout_ms`; `null` where the colleague sets none. */
  latency_floor_ms: number | null;
}

export interface DossierReliability {
  window_days: number;
  runs_total: number;
  runs_failed: number;
  /** `null` with no runs. Never `0` — see the module note. */
  failure_rate: number | null;
  p95_latency_ms: number | null;
  demotion_bar: DemotionBar;
}

/** The band, plus the demotion stamp when the sweep has written one. An absent
 *  stamp means "never demoted", which is a fact and not missing data. */
export interface DossierAutonomy {
  band: string;
  demoted_at?: string;
  demotion_reasons?: string[];
}

export interface DossierDistrict {
  process_code: string;
  name: string;
  quarter: string;
}

export interface Dossier {
  as_of: string;
  entity_id: string;
  /** The slug the portrait key is derived from (`artKeyFor`). */
  name: string;
  /** What a person calls her. `null` where the entity was never given one. */
  display_name: string | null;
  role: string | null;
  type: string;
  status: string;
  version: number;
  charter_updated_at: string | null;
  retired_at: string | null;
  district: DossierDistrict | null;
  autonomy: DossierAutonomy;
  charter: {
    clauses: CharterClause[];
    /** Verbatim, so "in words" and "governance record" are two renderings of
     *  one thing rather than two sources that can disagree. */
    governance: Record<string, unknown>;
    authority: DossierAuthority[];
  };
  competencies: DossierCompetency[];
  reliability: DossierReliability;
  running_runs: number;
  open_approvals: number;
  absent: DossierAbsence[];
}

/**
 * One colleague's terms of engagement.
 *
 * A 404 means *this company has no such entity* — unknown and cross-tenant
 * alike, on purpose — so a caller must not translate it into "the dossier is
 * empty" any more than the district read may.
 */
export async function fetchDossier(entityId: string): Promise<Dossier> {
  return (
    await api.get<Dossier>(`/ai/entities/${encodeURIComponent(entityId)}/dossier`)
  ).data;
}

/** The reason this field cannot be answered, or `null` where the platform did
 *  not name it as absent. No fallback sentence — see the module note. */
export function absenceOf(dossier: Dossier, field: string): string | null {
  return dossier.absent.find((item) => item.field === field)?.why ?? null;
}
