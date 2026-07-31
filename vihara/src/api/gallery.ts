/**
 * The Gallery's four reads (D6 §11, DRIVER D8; R-4 part P).
 *
 * §11 binds the surface to `strategy` (resolutions, reviews), `kpi.history`,
 * `twin` runs and the terminated roster. Three of the four have a door; the
 * fourth — the Seasons timeline — does not, and this module says so rather
 * than composing something that looks like one:
 *
 * **There is no Season object.** A season in the fixture is a *period* with a
 * name, a span, a story and an afterwards. Nothing on the backend stores any
 * of those four fields; `grep -ri season backend/src/ai` finds the forecast
 * engine's weekly seasonality and nothing else. What does exist is the
 * material a season is made of — the Resolutions adopted inside it and the KPI
 * series that either was or was not running at the time — so
 * `fetchSeasonMaterial` returns exactly that and the surface composes the
 * timeline from it. Naming a season is domain design (D8's E3/E4 shape) and it
 * is not smuggled in here as a fabricated wrapper.
 *
 * **`measured` is derived, never asserted.** The KPI series starts 2026-07-25
 * with no backfill by construction (LEARN §6.3), so whether a period was
 * measured is a question about `first_measurable_on`, and `firstMeasurableOn`
 * below is the one number the surface should ask.
 */
import { api } from "./client";
import { fetchRecords, type TenantRecordOut } from "./tenant";

/* ─────────────────────────────────────────────────── alumni (colleagues past) */

/**
 * A colleague who left. The row exists only where termination ran its
 * ceremony — `talent/router.py` skips soft-deleted entities with no stamp, on
 * the grounds that they are not Gallery records. Every count here comes off
 * that stamp, so a `null` is "the stamp did not carry it", never zero.
 */
export interface Alumnus {
  entity_id: string;
  name: string;
  /** The entity's system name — the stable key a portrait is filed under. */
  art_name: string;
  terminated_at: string | null;
  runs_total: number | null;
  runs_completed: number | null;
  memo_artifact_id: string | null;
}

export async function fetchAlumni(): Promise<Alumnus[]> {
  return (await api.get<Alumnus[]>("/ai/talent/colleagues-past")).data;
}

/* ──────────────────────────────────────────────────────────────── mandates */

/**
 * A mandate whose review has come due. The payload is the tenant record's own
 * `data` blob with its id folded in, so every field but `record_id` is
 * whatever the Mandate object carries — typed loosely on purpose, because
 * narrowing it here would be this module asserting a tenant schema it does not
 * own.
 */
export interface DueMandate {
  record_id: string;
  title?: string;
  target?: string;
  review_due?: string;
  status?: string;
  [key: string]: unknown;
}

export async function fetchReviewsDue(): Promise<DueMandate[]> {
  const { data } = await api.get<{ mandates: DueMandate[]; count: number }>(
    "/ai/strategy/reviews-due",
  );
  return data.mandates;
}

/**
 * Predicted vs realized for one mandate — the Gallery's ghost.
 *
 * `measurable: false` with a populated `missing` is a legitimate outcome and
 * the reason this is not just two numbers: "we cannot tell" is a third answer.
 * `predicted_value` is `null` where nothing was predicted — an untested
 * promotion has a realized value and no ghost, and the surface renders that
 * absence as a sentence rather than as a zero (D6 §11's second honesty rule).
 *
 * `honesty_grade` rides beside the verdict deliberately: a missed mandate whose
 * proposition was graded `replay` is a different failure from one that was
 * never tested at all.
 */
export interface RealizedMandate {
  mandate_id: string;
  kpi_key: string | null;
  predicted_value: number | null;
  predicted_from: string | null;
  realized_value: number | null;
  measurable: boolean;
  missing: string[];
  verdict: string | null;
  direction: string | null;
  honesty_grade: string | null;
  twin_run_id: string | null;
  review_fields: Record<string, unknown>;
}

export async function fetchRealized(mandateId: string): Promise<RealizedMandate> {
  return (
    await api.get<RealizedMandate>(
      `/ai/strategy/mandates/${encodeURIComponent(mandateId)}/realized`,
    )
  ).data;
}

/* ───────────────────────────────────────────────────────────── KPI history */

export interface KpiHistoryPoint {
  captured_on: string;
  /** `null` on a day the KPI could not be measured. The point is still
   * returned — an absence in the middle of a series is information. */
  value: number | null;
  measurable: boolean;
  missing: string[];
  baseline_value: number | null;
  sample_size: number | null;
}

export interface KpiSeries {
  key: string;
  display_name: string;
  unit: string;
  /** `null` means "never measurable *in this window*", not "never". */
  first_measurable_on: string | null;
  measurable_days: number;
  points: KpiHistoryPoint[];
}

export interface KpiHistory {
  from: string;
  to: string;
  series: KpiSeries[];
}

/**
 * The recorded series. Empty is the correct answer before the snapshot job has
 * ever run, and a range wider than the 400-day retention window is refused by
 * the backend rather than silently truncated — so a caller that widens the
 * range on an empty result gets a 400, which is the honest outcome.
 *
 * Naming an unknown key is a 400 too, on the grounds that an empty series for
 * a typo looks identical to "no data yet".
 */
export async function fetchKpiHistory(options?: {
  keys?: string[];
  from?: string;
  to?: string;
}): Promise<KpiHistory> {
  const params: Record<string, string> = {};
  if (options?.keys !== undefined && options.keys.length > 0) {
    params["keys"] = options.keys.join(",");
  }
  if (options?.from !== undefined) params["from"] = options.from;
  if (options?.to !== undefined) params["to"] = options.to;
  return (await api.get<KpiHistory>("/ai/kpi/history", { params })).data;
}

/** The earliest day any of these series became measurable, or `null` when none
 * of them ever did. This is the whole "was this season measured" question, and
 * it is one derivation rather than a flag every caller re-invents. */
export function firstMeasurableOn(history: KpiHistory): string | null {
  const days = history.series
    .map((series) => series.first_measurable_on)
    .filter((day): day is string => day !== null)
    .sort();
  return days[0] ?? null;
}

/* ────────────────────────────────────────────────────────────────── seasons */

/**
 * What a season is made of, since a season itself is not stored.
 *
 * `resolutions` are the tenant's Resolution records — the same rows the
 * estate's `monuments` block projects, read whole here because the timeline
 * needs the adopted-on date and the concerns-module, not just a title.
 * `history` is the KPI record over the same span, so the surface can mark the
 * seasons that predate it as *unmeasured* rather than as *flat*.
 */
export interface SeasonMaterial {
  resolutions: TenantRecordOut[];
  history: KpiHistory;
}

export async function fetchSeasonMaterial(options?: {
  from?: string;
  to?: string;
}): Promise<SeasonMaterial> {
  const [resolutions, history] = await Promise.all([
    fetchRecords("Resolution"),
    fetchKpiHistory(options),
  ]);
  return { resolutions, history };
}
