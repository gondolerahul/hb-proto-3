/**
 * Fixtures for the Decisions family — the Boardroom (D6 §8) and the Standup
 * (D6 §10). Shaped to the D5 contracts so R-4 is a swap of the data source:
 *
 *   Boardroom  `strategy/*` (shipped) · `kpi.business` · `kpi.history` ·
 *              `twin` grades (read-only) · `POST /ai/strategy/adopt` (T2)
 *   Standup    `executions` (yesterday) · `trays` · `kpi.history` (deltas)
 *
 * Two conventions in here are load-bearing rather than cosmetic:
 *
 * 1. **`Grade.twinRunId` is `null` only for `untested`.** STRAT's pipeline has
 *    `_GRADES_NEEDING_A_RUN = {replay, forecast, unknown}` and `untested` is the
 *    single value that needs no run behind it. The surface renders that absence
 *    as the *structural* tell between `untested` and `unknown` — see the grade
 *    idiom table in `BoardroomSurface.tsx`.
 *
 * 2. **`Grade.means` is the engine's sentence, not the UI's.** It is
 *    `TwinRunView.grade_means` off the wire (`src/api/twin.ts`). The client is
 *    given no way to speak about a grade, and it is given no way to paraphrase
 *    one either.
 *
 * `expected` and `moved` are `null` wherever nothing projects the figure. Two of
 * the four propositions below have no expected effect on purpose: a board that
 * only ever sees a number attached to a bet learns that every bet has one.
 *
 * Content is deliberately awkward — a colleague on probation with a second
 * reversal this week, a proposition the Glasshouse ran and could not grade, a
 * KPI with no June to compare against, and a colleague who did nothing yesterday
 * and did not invent work to fill the day.
 *
 * Colleague ids are the same agents as `estate.ts`'s `COLLEAGUES`; the join is
 * made at R-4 rather than here, so this file stays a flat fixture.
 */

/** D4 §3.1 / manifest contract §65 — four values, not three. */
export type HonestyGrade = "replay" | "forecast" | "untested" | "unknown";

export interface Grade {
  grade: HonestyGrade;
  /** The run the grade rests on. `null` **only** for `untested`. */
  twinRunId: string | null;
  /** `TwinRunView.grade_means` — the engine's words, never composed here. */
  means: string;
}

export interface AgendaItem {
  label: string;
  detail: string;
  drift: "behind" | "ahead" | "flat" | "flagged" | "no-comparison";
  /** `null` where there is no comparable prior figure. Never rendered as 0. */
  delta: string | null;
}

export interface Proposition {
  id: string;
  title: string;
  because: string;
  concerns: string;
  raisedAt: string;
  levers: { label: string; from: string; to: string }[];
  /** `null` when nothing projects an effect. Renders as no line at all. */
  expected: { label: string; value: string } | null;
  grade: Grade;
  /**
   * The id `POST /ai/strategy/adopt` would mint. Pre-bound because the prototype
   * has no server to mint it — never composed at render time, and never shown
   * before the adoption happens.
   */
  resolutionId: string;
}

export interface Minute {
  id: string;
  at: string;
  text: string;
  kind: "note" | "raised" | "resolution";
}

export const BOARD = {
  title: "Q3 review",
  period: "Q3 FY26",
  sitting: "SIT-0031",
  openedAt: "09:02",
  /** No backfill before this date. The agenda says so rather than drawing a gap. */
  seriesStartsOn: "25 Jul 2026",
};

export const AGENDA: AgendaItem[] = [
  {
    label: "Days sales outstanding",
    detail: "38 days against a target of 30, and rising since June.",
    drift: "behind",
    delta: "+9d",
  },
  {
    label: "Care CSAT",
    detail: "Flat at 4.6 for six weeks. Neither the complaint mix nor the volume moved.",
    drift: "flat",
    delta: null,
  },
  {
    label: "P19 · Renewals",
    detail: "Two accounts lapsed without a renewal conversation. Nobody was assigned to them.",
    drift: "flagged",
    delta: "2",
  },
  {
    label: "Quote win rate",
    detail:
      "61% this week. The KPI series starts 25 Jul with no backfill, so there is no June figure to compare against and I am not showing you a drift I cannot support.",
    drift: "no-comparison",
    delta: null,
  },
];

export const PROPOSITIONS: Proposition[] = [
  {
    id: "PROP-114",
    title: "Raise the chase cadence on overdue invoices to every four days",
    because:
      "Every overdue invoice we hold past day 40 costs about as much in working capital as the chase costs in attention, and Meera is idle for two of every seven days. Four days is the shortest interval Anjali's dunning ladder still reads as firm rather than frantic. I have not simulated it — there is no past window where we ran this cadence, so there is nothing to replay and nothing honest to model forward from.",
    concerns: "P08 · Order to Cash",
    raisedAt: "09:14",
    levers: [{ label: "Chase interval", from: "every 7 days", to: "every 4 days" }],
    expected: null,
    grade: {
      grade: "untested",
      twinRunId: null,
      means: "Nobody has tried this. There is no run behind it.",
    },
    resolutionId: "R-14",
  },
  {
    id: "PROP-113",
    title: "Above ₹50,000, drop the third reminder and call instead",
    because:
      "The third reminder is answered eleven per cent of the time. A call is answered just over half the time and costs ₹18. On your real Q2 signals the change collected sooner on six of the eleven invoices it touched and made no difference on the other five.",
    concerns: "P08 · Order to Cash",
    raisedAt: "09:19",
    levers: [
      { label: "Third reminder", from: "email", to: "call" },
      { label: "Threshold", from: "—", to: "₹50,000" },
    ],
    expected: { label: "Collected sooner", value: "9 days on 6 of 11 invoices" },
    grade: {
      grade: "replay",
      twinRunId: "TWR-2208",
      means: "Re-ran the real signals of a past window through the changed rule.",
    },
    resolutionId: "R-15",
  },
  {
    id: "PROP-111",
    title: "Move Kanwal Trading to prepaid terms",
    because:
      "KT-2291 is 47 days overdue on ₹96,500 and two reminders have gone unanswered. Prepaid terms end the exposure. It would also end the relationship if they read it as an accusation, and I have no way to weigh that from signals.",
    concerns: "P08 · Order to Cash",
    raisedAt: "08:58",
    levers: [{ label: "Terms", from: "net 30", to: "prepaid" }],
    expected: null,
    grade: {
      grade: "unknown",
      twinRunId: "TWR-2196",
      means: "The run completed and the result could not be graded — too few comparable past cases.",
    },
    resolutionId: "R-16",
  },
  {
    id: "PROP-108",
    title: "Hire a second collections colleague in September",
    because:
      "Meera is at capacity for two weeks of every month and the overdue book has grown faster than the ledger. A second colleague at A1 costs ₹2,400 a month to run. There is no past window with two collections colleagues in it, so this is modelled forward rather than replayed, and a model of a hire is a model of a person.",
    concerns: "P08 · Order to Cash",
    raisedAt: "09:26",
    levers: [{ label: "Collections headcount", from: "1", to: "2" }],
    expected: { label: "Days sales outstanding", value: "34d by mid-October" },
    grade: {
      grade: "forecast",
      twinRunId: "TWR-2181",
      means: "Modelled forward. No past window matched the change closely enough to replay.",
    },
    resolutionId: "R-17",
  },
];

export const MINUTES: Minute[] = [
  { id: "MIN-1", at: "09:02", text: "Pragya opened on the DSO drift. Nine days since June, no single cause.", kind: "note" },
  { id: "MIN-2", at: "09:07", text: "Margin on the Coromandel account questioned. No answer today — Farhan to bring the posting.", kind: "note" },
  { id: "MIN-3", at: "09:11", text: "Pricing raised as a separate matter. Parked for the Q4 board.", kind: "note" },
  { id: "MIN-4", at: "09:14", text: "Chase cadence tabled as PROP-114.", kind: "raised" },
];

/* ============================================================== THE STANDUP */

export interface StandupLine {
  id: string;
  who: {
    id: string;
    name: string;
    role: string;
    standing: "associate" | "probationer" | "senior";
  };
  /** When the colleague finished preparing it. The voice is still Pragya's. */
  preparedAt: string;
  /**
   * Pragya's sentence about the colleague, in her voice, in the third person.
   * **Never the colleague's own words** (L2) — a colleague's raw output appears
   * in `facts` as data, never as prose.
   */
  line: string;
  facts: { label: string; value: string }[];
  /** The KPI this line moved. `null` where nothing moved, or nothing measured it. */
  moved: { label: string; value: string } | null;
  /** A tray card this line is waiting on. Gold is sanctioned here: needs-you. */
  needsYou: { trayId: string; ask: string } | null;
  /** Present only where the line carries a bet the Glasshouse has an opinion on. */
  grade: Grade | null;
}

export const STANDUP_DAY = {
  label: "Thursday 30 July",
  /** L2: the whole surface is one voice. The header says so in words. */
  covering: "yesterday",
  budgetSeconds: 90,
};

export const STANDUP: StandupLine[] = [
  {
    id: "SU-1",
    who: { id: "AGT-046", name: "Meera", role: "Collections", standing: "associate" },
    preparedAt: "07:04",
    line: "Meera cleared eleven of the fourteen chases she picked up and matched INV-4471 against its goods receipt and its purchase order. She is holding one release for you — ₹1,84,000 to Sundar Textiles, thirty days old today, nothing in dispute.",
    facts: [
      { label: "Runs", value: "34" },
      { label: "Signals handled", value: "288" },
      { label: "Exceptions", value: "1 · a missing GRN on INV-4462" },
      { label: "Waiting on you", value: "34 min" },
    ],
    moved: { label: "Days sales outstanding", value: "38d, from 41d" },
    needsYou: { trayId: "HITL-8841", ask: "Release ₹1,84,000 to Sundar Textiles" },
    grade: null,
  },
  {
    id: "SU-2",
    who: { id: "AGT-038", name: "Ravi", role: "Reconciliation", standing: "probationer" },
    preparedAt: "07:11",
    line: "Ravi reconciled fourteen invoices and got twelve of them right. Two he posted into the wrong quarter; I reversed both before the books closed. That is his second reversal this week and his probation ends on Friday, so this is the week you would want to look at him yourself.",
    facts: [
      { label: "Runs", value: "18" },
      { label: "Reconciled", value: "14 · 12 clean" },
      { label: "Reversals", value: "2 · both Q2/Q3 boundary" },
      { label: "Probation ends", value: "Fri 31 Jul" },
    ],
    moved: null,
    needsYou: null,
    grade: null,
  },
  {
    id: "SU-3",
    who: { id: "AGT-041", name: "Anjali", role: "Dunning", standing: "probationer" },
    preparedAt: "07:16",
    line: "Anjali drafted the third reminder to Kanwal Trading and stopped there, because the tone changes at the third rung of the ladder and she is not allowed to change tone on her own. It has been sitting for an hour and fifty-two minutes.",
    facts: [
      { label: "Runs", value: "9" },
      { label: "Drafted", value: "3 reminders" },
      { label: "Held for you", value: "1 · KT-2291" },
      { label: "Waiting", value: "112 min" },
    ],
    moved: null,
    needsYou: { trayId: "HITL-8839", ask: "Send the third reminder to Kanwal Trading" },
    grade: null,
  },
  {
    id: "SU-4",
    who: { id: "AGT-013", name: "Devika", role: "Quoting", standing: "senior" },
    preparedAt: "07:19",
    line: "Devika had no runs yesterday. Nothing came into quoting after Monday and she did not invent work to fill the day. She has asked one thing: whether quoting should widen to the whole Ashoka group rather than the one buying entity.",
    facts: [
      { label: "Runs", value: "0" },
      { label: "Last quote", value: "Mon 27 Jul" },
      { label: "Asked", value: "1 · scope of the Ashoka group" },
    ],
    moved: null,
    needsYou: null,
    grade: {
      grade: "forecast",
      twinRunId: "TWR-2214",
      means: "Modelled forward. No past window matched the change closely enough to replay.",
    },
  },
  {
    id: "SU-5",
    who: { id: "AGT-092", name: "Farhan", role: "Bookkeeping", standing: "associate" },
    preparedAt: "07:22",
    line: "Farhan posted thirty-one entries and caught a duplicate against Bhagwati Mills before it reached the ledger. Nothing has been unreconciled for more than seven days since Tuesday.",
    facts: [
      { label: "Runs", value: "27" },
      { label: "Entries posted", value: "31" },
      { label: "Duplicates caught", value: "1 · ₹41,600" },
    ],
    moved: { label: "Unreconciled over 7 days", value: "0" },
    needsYou: null,
    grade: null,
  },
];

// ============================================================================
// TABLING A MATTER — the owner-initiated path (owner review D, 2026-07-30)
// ============================================================================

/**
 * The review asked: *how do I brainstorm here — say I want to develop a new
 * marketing plan?* The honest answer was that there was no way to, because the
 * Boardroom only rendered propositions **Pragya** raised from KPI drift. An
 * owner arriving with a thought had nowhere to put it.
 *
 * What closes that is not a chat panel. It is the **front of the same pipeline**:
 * a matter the owner tables becomes Minutes, the exchange becomes a Proposition,
 * and the Proposition adopts into a Resolution exactly as hers do. Anything else
 * would be a second way to make strategy, and STRAT's whole premise is that
 * there is one.
 *
 * Pragya's side of the exchange is scripted here because the prototype has no
 * model behind it. Two properties are load-bearing and are what R-4 must keep
 * when a real model replaces the script:
 *
 *  1. **She opens with what she already knows** — named figures from the estate,
 *     not enthusiasm. A strategy conversation that begins with "great idea!" has
 *     taught the owner nothing and cost them a turn.
 *  2. **She names what she cannot know.** Every matter here ends `untested`,
 *     because nothing has been simulated yet. She says so, and offers the
 *     Glasshouse rather than implying a forecast she does not have.
 */

export interface MatterQuestion {
  id: string;
  /** Her question, in her voice. */
  asks: string;
  /** Why she is asking — what the answer changes. Never omitted. */
  because: string;
  options: { label: string; /** What choosing this sets on the draft. */ sets: string }[];
}

export interface MatterScript {
  /** Lower-case words that route a typed matter to this script. */
  match: string[];
  /** How she restates the matter, so the owner can see she understood it. */
  reading: string;
  /** What she already knows, from the estate. Figures, not sentiment. */
  knows: { label: string; value: string; note: string }[];
  /** What she does not have and would need. */
  missing: string[];
  questions: MatterQuestion[];
  /** The proposition the exchange assembles into. */
  draft: {
    title: string;
    because: string;
    concerns: string;
    levers: { label: string; from: string; to: string }[];
    expected: { label: string; value: string } | null;
    resolutionId: string;
  };
}

const UNTESTED_MEANS =
  "Nothing has been simulated. There is no past window where we ran this, so there is nothing to replay and nothing honest to model forward from.";

export const MATTER_SCRIPTS: MatterScript[] = [
  {
    match: ["marketing", "campaign", "brand", "awareness", "festive", "promotion"],
    reading:
      "A marketing plan — you want to spend to bring more work in, and you want to know what it would cost and what it would move.",
    knows: [
      {
        label: "Quote win rate",
        value: "61%",
        note: "Acquisition is ahead of its target of 55, so the work we get, we mostly close.",
      },
      {
        label: "Leads this month",
        value: "38",
        note: "All inbound. Nothing in the estate currently generates a lead.",
      },
      {
        label: "Order-to-cash",
        value: "38 days",
        note: "Collections is nine days over target, so more work billed is more money in transit before it is money.",
      },
    ],
    missing: [
      "any past marketing spend to compare against — this would be the first",
      "a cost-per-lead figure, which only exists once something has run",
      "channel consent posture for outbound social (KAR-05 gates it)",
    ],
    questions: [
      {
        id: "q-goal",
        asks: "What is this plan for — more leads, or better ones?",
        because:
          "It picks the lever. More leads means volume and a wider net; better leads means targeting, and a smaller spend that Devika can actually keep up with.",
        options: [
          { label: "More leads", sets: "goal = volume" },
          { label: "Better leads", sets: "goal = qualification" },
        ],
      },
      {
        id: "q-ceiling",
        asks: "What is the most you would spend in a month before you wanted to stop and look?",
        because:
          "It becomes the campaign's budget envelope. Work stops at the envelope rather than asking you mid-month, and the protected reserve sits behind it.",
        options: [
          { label: "₹25,000", sets: "envelope = ₹25,000/month" },
          { label: "₹60,000", sets: "envelope = ₹60,000/month" },
          { label: "You tell me what it needs", sets: "envelope = Pragya proposes" },
        ],
      },
      {
        id: "q-who",
        asks: "Should I bring in a colleague for this, or extend Devika?",
        because:
          "Devika quotes; she does not prospect. A campaign is a different charter, and giving it to her would blur what she is measured on.",
        options: [
          { label: "Bring in a colleague", sets: "new colleague, at A1" },
          { label: "Extend Devika", sets: "amend Devika's charter" },
        ],
      },
    ],
    draft: {
      title: "Run a festive-season acquisition campaign for one month",
      because:
        "We close 61% of what we quote but generate none of it — every lead we have is inbound. One bounded month of spend would tell us what a lead costs us, which is the number every later marketing decision needs and the one number we do not have.",
      concerns:
        "More work billed lands on a collections function already nine days over target, so this raises exposure before it raises cash. And this is our first spend of its kind, so I can offer you a bounded experiment, not a projection.",
      levers: [
        { label: "campaign envelope", from: "₹0", to: "₹25,000/mo" },
        { label: "acquisition colleagues", from: "1", to: "2" },
        { label: "lead source", from: "inbound only", to: "inbound + campaign" },
      ],
      // Nothing projects an effect: this is the first campaign of its kind.
      expected: null,
      resolutionId: "R-19",
    },
  },
  {
    match: ["price", "pricing", "rate", "discount", "margin"],
    reading:
      "Pricing — you are asking whether what we charge is right, and what moving it would do.",
    knows: [
      {
        label: "Quote win rate",
        value: "61%",
        note: "Well above the target of 55, which is usually a sign there is room to charge more.",
      },
      {
        label: "Quotes lost on price",
        value: "4 of 27",
        note: "The stated reason in the record. Most losses were not about price.",
      },
      {
        label: "Days sales outstanding",
        value: "38 days",
        note: "A higher price on slower-paying accounts widens the gap before it narrows it.",
      },
    ],
    missing: [
      "any competitor price we hold on the record",
      "a segment breakdown — the win rate is one number across all customers",
    ],
    questions: [
      {
        id: "q-direction",
        asks: "Up across the board, or up only where we are winning easily?",
        because:
          "A flat rise is one change I can make once. A segmented rise needs a segment definition first, which is a schema change and a slower path.",
        options: [
          { label: "Across the board", sets: "flat +5%" },
          { label: "Only where we win easily", sets: "segmented, needs a definition" },
        ],
      },
      {
        id: "q-existing",
        asks: "Does this touch quotes already out?",
        because:
          "Repricing a live quote is a different act from repricing the list — it reaches a customer who has already seen a number.",
        options: [
          { label: "New quotes only", sets: "effective on new quotes" },
          { label: "Everything not yet accepted", sets: "reprice open quotes" },
        ],
      },
    ],
    draft: {
      title: "Raise list prices 5% on new quotes",
      because:
        "We win 61% of quotes against a target of 55, and only 4 of 27 losses named price as the reason. That combination usually means the list is under-priced. A 5% rise is small enough to read the effect on win rate without losing a season.",
      concerns:
        "The win rate is one number across every customer, so a flat rise is blunt where a segmented one would be precise. And a higher price on accounts already paying at 38 days widens the exposure before it improves the margin.",
      levers: [
        { label: "list price", from: "baseline", to: "+5%" },
        { label: "applies to", from: "—", to: "new quotes only" },
      ],
      expected: null,
      resolutionId: "R-20",
    },
  },
];

/** The fallback: she is honest about not recognising the matter. */
export const MATTER_FALLBACK: MatterScript = {
  match: [],
  reading:
    "I have this down as tabled. I do not have a read on it yet — nothing in the estate measures it, so I would be guessing if I opened with a figure.",
  knows: [],
  missing: [
    "any KPI in the estate that this moves",
    "a past decision of this shape to reason from",
  ],
  questions: [
    {
      id: "q-what",
      asks: "What would tell us this had worked?",
      because:
        "Whatever you name becomes the measure, and without one I cannot bring you a review of it later — only an anecdote.",
      options: [
        { label: "A number I already see", sets: "measure = existing KPI" },
        { label: "Something we do not measure yet", sets: "measure = new, needs defining" },
      ],
    },
    {
      id: "q-reversible",
      asks: "If it goes badly, can we simply stop?",
      because:
        "A reversible matter can start at A1 and be watched. An irreversible one belongs in the Glasshouse before it belongs in the estate.",
      options: [
        { label: "We can stop any time", sets: "reversible" },
        { label: "Not really", sets: "irreversible — Glasshouse first" },
      ],
    },
  ],
  draft: {
    title: "Tabled for the next sitting, with a measure attached",
    because:
      "Nothing in the estate currently measures this, so the first useful step is agreeing what would count as it having worked. That is what makes a review possible later.",
    concerns:
      "I am carrying no evidence on this at all. Everything above is your reasoning, recorded, not mine.",
    levers: [],
    expected: null,
    resolutionId: "R-21",
  },
};

export const UNTESTED_GRADE: Grade = {
  grade: "untested",
  twinRunId: null,
  means: UNTESTED_MEANS,
};

/** Route a typed matter to a script. Word-boundary, so "repricing" still hits. */
export function scriptFor(matter: string): MatterScript {
  const text = matter.toLowerCase();
  for (const s of MATTER_SCRIPTS) {
    if (s.match.some((w) => text.includes(w))) return s;
  }
  return MATTER_FALLBACK;
}
