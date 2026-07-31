/**
 * The Glasshouse (D6 §12) — the twin plane.
 *
 * Bound to `twin` (scenarios, runs, grades, forecast) and `evolution` (canary).
 *
 * Two properties of this fixture are load-bearing rather than cosmetic:
 *
 *  1. **Every scenario carries its honesty grade, and the grade determines what
 *     may be shown.** A `forecast` may show a projected figure. An `untested`
 *     scenario may not show one at all — there is nothing behind it — so its
 *     `twin` reading is `null` and renders as absent, never as a zero.
 *  2. **Cost is visible and cheap by design.** Twin spend is tenant-initiated
 *     (charter decision 6), so a running scenario shows what it cost. Keeping a
 *     what-if cheap — bounded windows, cached baselines, no re-embedding — is a
 *     design requirement here, not an optimisation.
 */

export type HonestyGrade = "replay" | "forecast" | "untested" | "unknown";

export interface ScenarioGrade {
  grade: HonestyGrade;
  /** The run behind it. `null` **only** for `untested`. */
  twinRunId: string | null;
  /** The engine's own words. Never composed in the surface. */
  means: string;
}

export interface Lever {
  key: string;
  label: string;
  unit: string;
  /** What the real estate runs at now. */
  real: number;
  /** What this scenario sets it to. */
  twin: number;
  min: number;
  max: number;
  step: number;
}

export interface Scenario {
  id: string;
  label: string;
  /** What the owner was asking. */
  question: string;
  grade: ScenarioGrade;
  levers: Lever[];
  /**
   * The measure both planes report. `twin` is `null` when the grade is
   * `untested` — nothing ran, so there is no reading, and no reading renders as
   * nothing at all.
   */
  measure: { label: string; unit: string; real: number; twin: number | null };
  /** What running it cost. `null` for a scenario that has not been run. */
  costINR: number | null;
  /** Where it sits on the promotion chain, if anywhere. */
  promotion: "none" | "diffed" | "approved" | "board-built" | "canary" | "ga";
}

const MEANS = {
  replay:
    "Re-ran against a real past window. Every input is something that actually happened, so the difference is attributable.",
  forecast:
    "Modelled forward from the baseline. No past window ran this, so the reading is a projection and carries the model's error, not the estate's.",
  untested:
    "Nothing has been simulated. There is no past window where we ran this, so there is nothing to replay and nothing honest to model forward from.",
  unknown:
    "The run completed but could not be graded — its baseline drifted mid-window, so the comparison is not sound.",
} as const;

export const SCENARIOS: Scenario[] = [
  {
    id: "S-14",
    label: "Chase cadence at four days",
    question: "If Meera chased every four days instead of every seven, what happens to DSO?",
    grade: { grade: "replay", twinRunId: "TWR-4471", means: MEANS.replay },
    levers: [
      { key: "cadence", label: "chase cadence", unit: "days", real: 7, twin: 4, min: 2, max: 14, step: 1 },
      { key: "collectors", label: "collectors", unit: "", real: 1, twin: 2, min: 1, max: 4, step: 1 },
    ],
    measure: { label: "Days sales outstanding", unit: "d", real: 38, twin: 31 },
    costINR: 14,
    promotion: "diffed",
  },
  {
    id: "S-15",
    label: "Two more collectors",
    question: "Does adding people help, or is the cadence the constraint?",
    grade: { grade: "forecast", twinRunId: "TWR-4482", means: MEANS.forecast },
    levers: [
      { key: "collectors", label: "collectors", unit: "", real: 1, twin: 3, min: 1, max: 4, step: 1 },
    ],
    measure: { label: "Days sales outstanding", unit: "d", real: 38, twin: 34 },
    costINR: 9,
    promotion: "none",
  },
  {
    id: "S-16",
    label: "Price up five per cent",
    question: "What does a five per cent rise do to the win rate?",
    grade: { grade: "untested", twinRunId: null, means: MEANS.untested },
    levers: [
      { key: "price", label: "list price", unit: "%", real: 0, twin: 5, min: -10, max: 20, step: 1 },
    ],
    // No reading at all: nothing ran. Renders as absent, never as zero.
    measure: { label: "Quote win rate", unit: "%", real: 61, twin: null },
    costINR: null,
    promotion: "none",
  },
  {
    id: "S-13",
    label: "Expand to Pune",
    question: "Could a second territory carry its own collections?",
    grade: { grade: "unknown", twinRunId: "TWR-4390", means: MEANS.unknown },
    levers: [
      { key: "territories", label: "territories", unit: "", real: 1, twin: 2, min: 1, max: 3, step: 1 },
    ],
    measure: { label: "Days sales outstanding", unit: "d", real: 38, twin: 38 },
    costINR: 22,
    promotion: "none",
  },
];

/**
 * The promotion chain, in order. A scenario climbs it; it never skips.
 *
 * The two gold links are the certified ones — approval and GA both ask for a
 * passkey. Everything else on the chain is warm-white, because a step that
 * happens automatically is not asking anything of you.
 */
export const PROMOTION_CHAIN = [
  { key: "diffed", label: "Diff", what: "What would change, listed.", certified: false },
  { key: "approved", label: "Your approval", what: "A certified act. Asks for your passkey.", certified: true },
  { key: "board-built", label: "Board build", what: "The Meta-Agent board assembles it.", certified: false },
  { key: "canary", label: "Canary", what: "Runs beside the real on a slice, watched.", certified: false },
  { key: "ga", label: "General", what: "A certified act. The estate adopts it.", certified: true },
] as const;

/**
 * The Glasshouse's own spend, this month.
 *
 * Tenant-initiated (charter decision 6), which is why it is shown at all: a cost
 * the tenant chose to incur is a cost they are owed a number for. It is
 * deliberately small, and the surface says why.
 */
export const TWIN_SPEND = {
  monthINR: 218,
  runs: 19,
  /** Why it is cheap, in the surface's own words. */
  note: "Bounded windows, cached baselines, and no re-embedding. A what-if that costs real money is a what-if nobody runs.",
};
