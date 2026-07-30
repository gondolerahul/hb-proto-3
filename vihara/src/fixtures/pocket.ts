/**
 * The Pocket Desk's data (D6 §16–18, R-3c §3.3).
 *
 * Shaped to the three registry entries the Desk composes — `primitive.figure`,
 * `primitive.kpi-dial` and `narrative.still-line` — and to `surface.line_pins`
 * in LEARN's preference store, which is where a pin actually lives (LINE §6: the
 * namespace already exists, so a pin is a code-reviewed key rather than a new
 * table).
 *
 * Four properties of this file are load-bearing rather than decorative.
 *
 * **The vitals are derived, never restated.** Every number in the band is
 * computed here from `fixtures/estate.ts` — the same rows the Still Surface, the
 * Terrace and the Tray read. The phone and the desk disagreeing about the estate
 * is the failure a person notices immediately and never forgives, and a fixture
 * that *copies* a figure is where that divergence starts.
 *
 * **A dial's reading may be absent, and that is the primary state.** The KPI
 * series starts 2026-07-25 with no backfill (D6 §11), so for roughly a quarter a
 * tenant holds measures with no point in them yet. `current: null` renders as no
 * figure at all — never a zero, never a dash (DESIGN_CONTRACT §7.1) — and one of
 * the three cards pinned on the first frame is in exactly that state, because a
 * young estate is what the owner will actually see.
 *
 * **The only comparison a young series supports is against its own first day.**
 * There is no "last week" to divide by, so a dial carries `since` — the first
 * point in its series, with the date — and not a week-on-week drift the platform
 * cannot compute. Where even that is missing the trend renders as a sentence
 * saying so.
 *
 * **A dial is a suffix-unit measure; money is a figure.** `kpi-dial` carries a
 * number, a unit that follows it, and a target the meter is computed from rather
 * than told. Anything with a ₹ in front of it is a `figure` and carries the
 * wire's own string — which is what stops the Desk from trying to draw a meter
 * for a rupee amount with no target to draw it against.
 */

import { COMPANY, DISTRICTS, DISTRICT_ROOMS, INVOICES, STILL, TRAY } from "./estate";

/* ================================================================== vitals
   The slice of the estate that is never pinnable away. Three readings and one
   sentence: enough to answer "is anything wrong", and nothing that would make
   this a Terrace with the map cut off. */

export interface VitalCell {
  /** Rendered as an eyebrow, so it is stored in sentence case and uppercased by
   *  the surface — and kept to two short words, which is all a third of a phone
   *  will hold at the eyebrow's tracking. */
  label: string;
  figure: string;
}

/** The pulse the Still Surface reads, summed the same way it sums it. */
const SIGNALS_AN_HOUR = DISTRICTS.reduce((n, d) => n + d.signalsPerHour, 0);

/** The longest anything has waited, as the Tray's own header computes it.
 *  `null` where nothing is waiting: there is then no wait to report, and the
 *  cell does not appear at all rather than reporting "0m". */
const LONGEST_WAIT_MINUTES =
  TRAY.length === 0 ? null : Math.max(...TRAY.map((c) => c.waitedMinutes));

export const VITALS: {
  hour: number;
  headline: string;
  handsRaised: number;
  cells: VitalCell[];
} = {
  hour: COMPANY.localHour,
  /** `narrative.still-line` — the estate's own sentence, and the one piece of
   *  prose the product guarantees is present. */
  headline: STILL.headline,
  handsRaised: STILL.handsRaised,
  cells: [
    { label: "Collected this week", figure: `₹${STILL.figure.collected}` },
    { label: "Signals an hour", figure: `${SIGNALS_AN_HOUR}` },
    ...(LONGEST_WAIT_MINUTES === null
      ? []
      : [{ label: "Longest wait", figure: `${LONGEST_WAIT_MINUTES}m` }]),
  ],
};

/* ================================================================ readings */

/** `P08 · Collections`, composed from the estate's own row so the phone cannot
 *  invent a quarter the desk has never heard of. */
function whereOf(code: string): string {
  const d = DISTRICTS.find((x) => x.code === code)!;
  return `${d.code} · ${d.name}`;
}

interface ReadingBase {
  /** The value written into `surface.line_pins`. For a dial it is the KPI's own
   *  `kpi_key`, which is why there is no second field holding the same string. */
  id: string;
  /** Where the reading belongs, already composed for display. */
  where: string;
}

/**
 * `primitive.kpi-dial@1`. `title` is its prop; `current` and `since` are what
 * `kpi.current` and `kpi.series` resolved to.
 */
export interface DeskDial extends ReadingBase {
  kind: "dial";
  title: string;
  /** `null` where the series has produced no point yet. Renders as nothing. */
  current: { value: number } | null;
  /** The KPI's own target, where its definition carries one. Where it does not,
   *  there is no target — not a target of zero. */
  target: { value: number } | null;
  /** Follows the numeral: `38d`, `61%`, and empty for a bare count. */
  unit: string;
  betterWhen: "lower" | "higher";
  /** The measurement window, where the KPI's definition names one. */
  window: string | null;
  /** The first point in this KPI's series, which is the only comparison a
   *  series with no backfill can honestly offer. `null` where there is not even
   *  one earlier point. */
  since: { value: number; on: string } | null;
  /** `first_measurable_on` — when this KPI became measurable at all. */
  measuredFrom: string;
  /** Where `current` is null, the one sentence that says why. Never a dash. */
  absence: string | null;
}

/**
 * `primitive.figure@1`. `label` is its prop; the binding behind it —
 * `records.aggregate`, `loop.envelope`, `billing.wallet` — is deliberately not
 * carried, because C never draws a binding source and a field kept for a surface
 * that will not render it is a shape invented on spec.
 */
export interface DeskFigure extends ReadingBase {
  kind: "figure";
  label: string;
  /** The wire's own string, ₹ and Indian grouping included. `null` where the
   *  aggregate produced nothing. */
  current: { figure: string } | null;
  /** One line of what the figure is *of*. */
  detail: string | null;
  absence: string | null;
}

export type DeskReading = DeskDial | DeskFigure;

/* --------------------------------------------------- the aggregates, computed
   Both of these are worked out from the rows the estate already holds rather
   than typed in, so a change to the Registry Hall's ledger or the Money
   Quarter's envelope moves the phone with it. */

const OVERDUE = INVOICES.filter((r) => r.state === "overdue");

/** `₹96,500` → `96500`. The Hall stores what the wire sends, which is display
 *  text; an aggregate over it has to read the digits back out. */
const OVERDUE_TOTAL = OVERDUE.reduce(
  (n, r) => n + Number(r.amount.replace(/[^0-9]/g, "")),
  0,
);

const TREASURY = DISTRICT_ROOMS["P08"]!.treasury;

const rupees = (n: number): string => `₹${n.toLocaleString("en-IN")}`;

/**
 * Everything the Desk can hold, pinned or not.
 *
 * The set is deliberately awkward, because a Desk that only survives tidy
 * content has not been tested: one measure is behind its target *and* improving,
 * one has a real measured zero, one has a value with nothing to compare it
 * against, and one has no reading at all.
 */
export const READINGS: DeskReading[] = [
  {
    kind: "dial",
    id: "kpi.dso",
    title: "Days sales outstanding",
    where: whereOf("P08"),
    /* 38 against a target of 30 is `DISTRICTS.P08.kpi`; 44 on the twenty-fifth
       is the first point of the series (`RECORD.readings` in the Gallery). Both
       are true at once and the card says both — behind where it should be, and
       six days better than the day the record began. */
    current: { value: 38 },
    target: { value: 30 },
    unit: "d",
    betterWhen: "lower",
    window: null,
    since: { value: 44, on: "25 Jul" },
    measuredFrom: "25 Jul",
    absence: null,
  },
  {
    kind: "dial",
    id: "kpi.close_days",
    title: "Days to close the books",
    where: whereOf("P14"),
    /* The young state, pinned on the first frame on purpose. A close cannot be
       measured until a close happens, and the first one inside the series is
       July's — so this card is honestly empty for another week and has to look
       deliberate rather than broken. */
    current: null,
    target: null,
    unit: "d",
    betterWhen: "lower",
    window: null,
    since: null,
    measuredFrom: "25 Jul",
    absence: "The first close inside the series is July’s, and it happens in August.",
  },
  {
    kind: "figure",
    id: "fig.overdue",
    label: "Overdue, all quarters",
    where: "Across the estate",
    current: OVERDUE.length === 0 ? null : { figure: rupees(OVERDUE_TOTAL) },
    detail:
      OVERDUE.length === 0
        ? null
        : `across ${OVERDUE.length} invoices · oldest ${Math.max(...OVERDUE.map((r) => r.age))} days`,
    absence: null,
  },
  {
    kind: "dial",
    id: "kpi.win_rate",
    title: "Quote win rate",
    where: whereOf("P03"),
    /* A reading with nothing behind it. The Boardroom's agenda says why in her
       own words: there is no June figure, so there is no drift to show and the
       card refuses to draw one. */
    current: { value: 61 },
    target: { value: 55 },
    unit: "%",
    betterWhen: "higher",
    window: null,
    since: null,
    measuredFrom: "25 Jul",
    absence: null,
  },
  {
    kind: "dial",
    id: "kpi.unreconciled",
    title: "Unreconciled invoices",
    where: whereOf("P14"),
    /* A measured zero, and the reason both states have to exist on one surface:
       the Desk prints 0 where a zero was counted and nothing at all where
       nothing was counted, and those must not look alike. */
    current: { value: 0 },
    target: null,
    unit: "",
    betterWhen: "lower",
    window: "over 7 days",
    since: null,
    measuredFrom: "25 Jul",
    absence: null,
  },
  {
    kind: "figure",
    id: "fig.envelope",
    label: "Spent this month",
    where: whereOf("P08"),
    current: { figure: rupees(TREASURY.spentINR) },
    /* The reserve is stated rather than drawn. It is the one gold seam on the
       district room's gauge, and on a 390px column a second gold would have to
       argue with the raised hand in the band above — so here it is a sentence. */
    detail: `of ${rupees(TREASURY.capINR)} · ${rupees(TREASURY.reserveINR)} of it never drains`,
    absence: null,
  },
];

/**
 * `surface.line_pins`, as LEARN's preference store returns it: the key, the
 * value, and whether the store learned it or the owner said it. R-4 replaces
 * this constant with `fetchPreferences(LINE_PINS.key)` and writes back through
 * `writePreference` — the surface already treats it as a stored list, so the
 * swap is a loader and not a rewrite.
 *
 * Three pins, chosen the way an owner would: the measure they worry about, the
 * money, and the one they are waiting to see appear.
 */
export const LINE_PINS: { key: string; value: string[]; learned: boolean } = {
  key: "surface.line_pins",
  value: ["kpi.dso", "fig.overdue", "kpi.close_days"],
  learned: false,
};
