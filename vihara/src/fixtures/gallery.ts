/**
 * The Gallery — the growth journey (D6 §11).
 *
 * Shaped to §11's bindings: `strategy` (resolutions, reviews) for seasons and
 * mandates, the SEGA `evolution` version ledger for the diffs, `kpi.history` for
 * the record, and `twin` runs for the predicted-vs-realized ghosts.
 *
 * Three honesty rules bite in this file, and they are stated where they bite:
 *
 * 1. **`RECORD.startedOn` is 25 July 2026 and there is no backfill, by
 *    construction.** So `Season.measured` is `false` for four of five seasons —
 *    not "we lost the data", but "nothing was being recorded then". A season
 *    that was never measured carries no figures at all, and the surface says so
 *    rather than reconstructing any.
 * 2. **`Ghost.predicted` is `null` where nothing was predicted.** Never `0`. An
 *    untested promotion has a realized value and no ghost, and the surface
 *    renders the absence as a sentence.
 * 3. **`Mandate.resolution` is `null` where the mandate did not come from a
 *    resolution.** There is then nothing to walk back to, so the act is absent
 *    rather than drawn disabled over nothing.
 *
 * Content is deliberately awkward: a season in which nothing was built, a
 * connector that was dismantled, a colleague who never left probation, a
 * prediction that was wrong by seven days, a mandate adopted before the passkey
 * ceremony existed, and a mandate with no resolution behind it at all.
 */

import type { IconName } from "../components/Icon";
import type { Grade } from "./decisions";

/* ============================================================== the seasons */

/**
 * A season is a **period, not a date** — it has a name, a span and a story. The
 * timeline is meant to read as a life rather than as an axis, which is why the
 * span is a phrase and the length is a day count rather than two timestamps.
 */
export interface Season {
  id: string;
  name: string;
  /** The span as it should read. Never composed from two dates at render time. */
  span: string;
  days: number;
  current: boolean;
  /**
   * Was the KPI series running during this season. `false` for everything before
   * 25 July 2026 — the record does not reach back, and neither does this room.
   */
  measured: boolean;
  story: string;
  /** What came of it. `null` for the current season, which has no afterwards yet. */
  afterwards: string | null;
}

export const SEASONS: Season[] = [
  {
    id: "S-1",
    name: "The Opening",
    span: "12 – 29 March 2026",
    days: 18,
    current: false,
    measured: false,
    story:
      "You arrived with two spreadsheets and one question: who owes us money. Meera was seated on the fourteenth and spent her first two days reading the ledger without writing to it, which is the only reason her first chase landed on the right invoice.",
    afterwards:
      "Nine invoices were chased by hand in this season and six of them paid. That was enough to know the work was real, and not enough to know whether it was working.",
  },
  {
    id: "S-2",
    name: "Learning to Chase",
    span: "30 March – 10 May 2026",
    days: 42,
    current: false,
    measured: false,
    story:
      "The season everything was built in. A district went up around Collections, the books came off your laptop and onto a bridge, and you released money on your own signature for the first time. Three colleagues, one of them on probation the whole way through.",
    afterwards:
      "By the end of it the estate ran without you watching it, which turned out to be the season's actual product. The cadence it settled into was wrong, and it took another six weeks to find that out.",
  },
  {
    id: "S-3",
    name: "The Quiet Weeks",
    span: "11 May – 21 June 2026",
    days: 42,
    current: false,
    measured: false,
    story:
      "Nothing was built. Two colleagues were retired, one chase cadence was walked back to its resolution and adopted again fifteen days earlier, and a grace rule went in from the floor with no run behind it. A quiet season is not an idle one — it is the season the estate spent correcting itself.",
    afterwards:
      "Both changes made here are on the wall below, and one of them missed its prediction by seven days. That is the season worth reading twice.",
  },
  {
    id: "S-4",
    name: "Second Wind",
    span: "22 June – 24 July 2026",
    days: 33,
    current: false,
    measured: false,
    story:
      "Acquisition opened, Devika started quoting on her own authority, and a voice line went in for the accounts that stopped answering email. One colleague was hired into a role that turned out not to exist and left again inside three weeks.",
    afterwards:
      "The last thing this season did was start measuring. That is why it is the last season told entirely in words.",
  },
  {
    id: "S-5",
    name: "The Measured Days",
    span: "25 July 2026 – now",
    days: 5,
    current: true,
    measured: true,
    story:
      "The first season with a record behind it. Five days of it so far, which is five days more than every season above and nowhere near a trend.",
    /* No afterwards. It has not happened, so there is nothing here. */
    afterwards: null,
  },
];

/* ============================================================ the monuments */

/**
 * A monument is a thing that was raised and — usually — still stands.
 *
 * `by` carries a persona and gets a halftone bust; `entityId` with no `by` is a
 * district, a bridge or a system act, which has no persona and gets a seal
 * (art bible §7, direction C as the automatic fallback).
 */
export interface Monument {
  id: string;
  name: string;
  kind: "district" | "bridge" | "act";
  what: string;
  raisedOn: string;
  seasonId: string;
  /** True where the raising was a T2 act — the one thing on this surface that
      may spend gold, because gold means certified (§2.1). */
  certified: boolean;
  /** The colleague who raised it, where one did. `null` → an act of the estate. */
  by: { id: string; name: string; stillServing: boolean } | null;
  /** The entity the mark is struck from, when there is no persona. */
  entityId: string;
  /** `null` while it still stands. A date here means it is past. */
  dismantledOn: string | null;
  icon: IconName;
}

export const MONUMENTS: Monument[] = [
  {
    id: "MON-1",
    name: "The Collections district",
    kind: "district",
    what: "Three colleagues, one ledger, and the first quarter of the estate with a wall around it.",
    raisedOn: "2 April 2026",
    seasonId: "S-2",
    certified: false,
    by: null,
    entityId: "DIST-COLLECTIONS",
    dismantledOn: null,
    icon: "district",
  },
  {
    id: "MON-2",
    name: "The Zoho Books bridge",
    kind: "bridge",
    what: "The books stopped being a file you kept and became something your colleagues could read.",
    raisedOn: "14 April 2026",
    seasonId: "S-2",
    certified: false,
    by: null,
    entityId: "BRG-ZOHO",
    dismantledOn: null,
    icon: "ledger",
  },
  {
    id: "MON-3",
    name: "First money released on your signature",
    kind: "act",
    what: "₹86,000 to Coromandel Garments, approved with your passkey. The first act in the estate that could not be undone.",
    raisedOn: "3 May 2026",
    seasonId: "S-2",
    certified: true,
    by: { id: "AGT-046", name: "Meera", stillServing: true },
    entityId: "T2-0914",
    dismantledOn: null,
    icon: "key",
  },
  {
    id: "MON-4",
    name: "The Tally connector",
    kind: "bridge",
    what: "Stood for ten weeks and was closed when the books moved to Zoho. Everything it wrote is still in the record.",
    raisedOn: "21 April 2026",
    seasonId: "S-2",
    certified: false,
    by: null,
    entityId: "BRG-TALLY",
    dismantledOn: "2 July 2026",
    icon: "ledger",
  },
  {
    id: "MON-5",
    name: "The Acquisition district",
    kind: "district",
    what: "Devika quoting on her own authority up to ₹1,00,000, with nobody standing behind her chair.",
    raisedOn: "28 June 2026",
    seasonId: "S-4",
    certified: true,
    by: { id: "AGT-013", name: "Devika", stillServing: true },
    entityId: "DIST-ACQUISITION",
    dismantledOn: null,
    icon: "district",
  },
  {
    id: "MON-6",
    name: "The record begins",
    kind: "act",
    what: "The first day of the KPI series. Nothing before it was backfilled, and nothing before it can be.",
    raisedOn: "25 July 2026",
    seasonId: "S-5",
    certified: false,
    by: null,
    entityId: "SYS-KPI",
    dismantledOn: null,
    icon: "trend",
  },
];

/* ============================================================== the record */

/**
 * `kpi.history`, and the whole reason this surface must be designed young.
 *
 * `trendNeedsDays` / `firstTrendOn` are the room's **stated** threshold for
 * drawing a line, not a figure off the wire: §11 says the series has no backfill
 * and will be thin "for roughly a quarter", so the room commits to a quarter in
 * public rather than drawing a five-point chart and calling it a trend.
 */
export const RECORD = {
  startedOn: "25 July 2026",
  daysRecorded: 5,
  trendNeedsDays: 90,
  firstTrendOn: "23 October 2026",
  readings: [
    {
      label: "Days sales outstanding",
      reading: "41 days",
      recordedFrom: "25 July 2026",
      /** The first point in the series. Real, and five days old. */
      first: { value: "44 days", on: "25 July" },
    },
    {
      label: "Quotes answered same day",
      reading: "62%",
      /* Acquisition only opened this measure on the 28th, so there is no earlier
         point to compare with. `null` renders as no comparison at all. */
      recordedFrom: "28 July 2026",
      first: null,
    },
  ] as {
    label: string;
    reading: string;
    recordedFrom: string;
    first: { value: string; on: string } | null;
  }[],
};

/* ========================================== predicted vs realized — the ghost */

/**
 * Every promoted experiment, with what was predicted beside what happened.
 *
 * `predicted: null` is the untested case — promoted with no run behind it. It
 * renders the realized value **alone** plus a sentence saying no prediction was
 * made. A zero prediction would be a fabricated bet.
 */
export interface Ghost {
  id: string;
  label: string;
  what: string;
  promotedOn: string;
  seasonId: string;
  /** Appended to the figure exactly as written — `" days"`, `"%"`. */
  unit: string;
  predicted: number | null;
  realized: number;
  /** Which direction is an improvement. Drives the lamp; the word says it too. */
  better: "lower" | "higher";
  /** A figure with no denominator is a claim, not a measurement. */
  over: string;
  grade: Grade;
}

export const GHOSTS: Ghost[] = [
  {
    id: "GH-1",
    label: "Chase at thirty days instead of forty-five",
    what: "Meera's first reminder moved fifteen days earlier.",
    promotedOn: "4 June 2026",
    seasonId: "S-3",
    unit: " days",
    predicted: 34,
    realized: 41,
    better: "lower",
    over: "days sales outstanding across the 30 days after promotion, on 88 invoices",
    grade: {
      grade: "replay",
      twinRunId: "TWN-2214",
      means:
        "A replay of March through May with the new cadence, on the invoices that actually existed.",
    },
  },
  {
    id: "GH-2",
    label: "Seven days of grace for accounts that have never been late",
    what: "Adopted from the floor, with nothing run behind it first.",
    promotedOn: "21 May 2026",
    seasonId: "S-3",
    unit: " disputes",
    predicted: null,
    realized: 3,
    better: "lower",
    over: "disputes opened in the 30 days after promotion, across 41 never-late accounts",
    grade: {
      grade: "untested",
      twinRunId: null,
      means: "Never tried. There is no run behind this, so there was nothing to grade.",
    },
  },
  {
    id: "GH-3",
    label: "Voice before email above ₹1,00,000",
    what: "The big accounts get a call first and an email after it.",
    promotedOn: "12 July 2026",
    seasonId: "S-4",
    unit: "%",
    predicted: 61,
    realized: 68,
    better: "higher",
    over: "value recovered within 30 days, on the 14 invoices above ₹1,00,000",
    grade: {
      grade: "forecast",
      twinRunId: "TWN-2190",
      means: "A projection from two months of call outcomes, not a replay of them.",
    },
  },
  {
    id: "GH-4",
    label: "Anjali on dunning at A1",
    what: "A second colleague on reminders, every act still coming to you.",
    promotedOn: "28 June 2026",
    seasonId: "S-4",
    unit: " hours a week",
    predicted: 9,
    realized: 4,
    better: "higher",
    over: "your own time back, measured against the four weeks before she was seated",
    grade: {
      grade: "unknown",
      twinRunId: "TWN-2203",
      means: "The replay's inputs drifted halfway through, so this could not be graded.",
    },
  },
];

/* ============================================================= the mandates */

/** One step in the SEGA version ledger. `removed: null` is the first version. */
export interface MandateVersion {
  v: string;
  on: string;
  by: string;
  removed: string | null;
  added: string;
}

export interface Mandate {
  id: string;
  title: string;
  state: "in-force" | "superseded";
  /** The mandate that replaced it. Present only when superseded. */
  supersededBy: string | null;
  adoptedOn: string;
  seasonId: string;
  /**
   * The resolution it came from. `null` where it came from something else — and
   * then there is nothing to walk back to, so no act is offered.
   */
  resolution: { id: string; title: string } | null;
  /** The T2 act that adopted it. `null` → adopted without ceremony. */
  certifiedAs: string | null;
  /** Why there is no resolution, where there is none. */
  origin: string | null;
  versions: MandateVersion[];
}

export const MANDATES: Mandate[] = [
  {
    id: "M-9",
    title: "Chase at thirty days",
    state: "in-force",
    supersededBy: null,
    adoptedOn: "4 June 2026",
    seasonId: "S-3",
    resolution: { id: "R-14", title: "Bring days sales outstanding to thirty" },
    certifiedAs: "T2-1180",
    origin: null,
    versions: [
      {
        v: "v3",
        on: "4 June 2026",
        by: "you, on Meera's proposal",
        removed: "first reminder at forty-five days",
        added: "first reminder at thirty days",
      },
      {
        v: "v2",
        on: "27 April 2026",
        by: "you",
        removed: "one reminder, then escalate",
        added: "two reminders, then escalate",
      },
      {
        v: "v1",
        on: "2 April 2026",
        by: "you",
        removed: null,
        added: "chase overdue invoices at forty-five days",
      },
    ],
  },
  {
    id: "M-12",
    title: "Voice first above ₹1,00,000, email after",
    state: "in-force",
    supersededBy: null,
    adoptedOn: "12 July 2026",
    seasonId: "S-4",
    resolution: { id: "R-19", title: "Stop losing the large accounts to silence" },
    certifiedAs: "T2-1443",
    origin: null,
    versions: [
      {
        v: "v1",
        on: "12 July 2026",
        by: "you",
        removed: null,
        added: "call before the second reminder when the invoice is above ₹1,00,000",
      },
    ],
  },
  {
    id: "M-4",
    title: "Call before emailing above ₹1,00,000",
    state: "superseded",
    supersededBy: "M-12",
    adoptedOn: "19 May 2026",
    seasonId: "S-3",
    resolution: { id: "R-11", title: "The large accounts are not answering" },
    /* Adopted before mandates went through the passkey ceremony. Shown as an
       absence rather than back-dated into one. */
    certifiedAs: null,
    origin: null,
    versions: [
      {
        v: "v2",
        on: "31 May 2026",
        by: "you",
        removed: "call on the day the invoice ages past sixty days",
        added: "call on the day the invoice ages past forty-five days",
      },
      {
        v: "v1",
        on: "19 May 2026",
        by: "you",
        removed: null,
        added: "call before emailing when the invoice is above ₹1,00,000",
      },
    ],
  },
  {
    id: "M-15",
    title: "Email only for Ashoka Retail",
    state: "in-force",
    supersededBy: null,
    adoptedOn: "24 July 2026",
    seasonId: "S-4",
    /* No resolution behind it — so no walk-back exists, and the room says why. */
    resolution: null,
    certifiedAs: null,
    origin:
      "Their finance lead asked Meera to stop calling. She recorded the preference against the account, and it now binds every colleague rather than only her.",
    versions: [
      {
        v: "v1",
        on: "24 July 2026",
        by: "Meera, from a customer's request",
        removed: null,
        added: "no calls to Ashoka Retail; email only",
      },
    ],
  },
];

/* ======================================================= colleagues past */

/**
 * The wall of colleagues who are no longer serving. Their portraits are drained
 * (art bible §7.2): the past and the not-yet-real share a material, because
 * neither is currently true.
 */
export interface Alum {
  id: string;
  name: string;
  role: string;
  served: string;
  seasonLeftId: string;
  why: string;
}

export const ALUMNI: Alum[] = [
  {
    id: "AGT-021",
    name: "Kavya",
    role: "Quoting",
    served: "2 April – 19 May 2026",
    seasonLeftId: "S-3",
    why: "Retired when quoting moved to Devika with a wider charter. Her three hundred and forty quotes are still in the record and still carry her name.",
  },
  {
    id: "AGT-055",
    name: "Ishan",
    role: "Outreach",
    served: "24 June – 12 July 2026",
    seasonLeftId: "S-4",
    why: "Never left probation. Nineteen drafts in nineteen days and you approved four of them, so the two of you agreed the role was wrong rather than the colleague.",
  },
];

/**
 * One colleague still serving, shown on the same wall **undrained**. The
 * contrast is the point: without her, the drained material reads as a style
 * choice instead of as a statement about time.
 */
export const STILL_SERVING = {
  id: "AGT-046",
  name: "Meera",
  role: "Collections",
  served: "since 14 March 2026",
  note: "Seated in the first week and still chasing. In full colour on purpose — everyone else on this wall is past.",
};
