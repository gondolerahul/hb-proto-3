/**
 * The Talent Office (D6 §9) — brief → shortlist → interview → probation →
 * confirmation.
 *
 * Bound to the **Meta-Agent Board** (shipped, seven roles) for the shortlist,
 * `twin` for the interview (the interview *is* a twin session), the per-path
 * cost estimator (D5 §4.1, DRIVER §4) for cost per month, and
 * `certified.autonomy-change@1` for the hire.
 *
 * Four properties of this fixture are load-bearing rather than decorative, and
 * every one of them is a place where a tidier fixture would have been a lie:
 *
 *  1. **A candidate's cost per month may be `null`, and one is.** The estimator
 *     needs five comparable colleague-months inside the company and will not
 *     pool across tenants (DRIVER §4). Below the floor it returns nothing, so
 *     `costPerMonthINR` is `null` and `costAbsence` carries the sentence that
 *     says why. There is no `₹0` and no dash anywhere in this file.
 *  2. **A past case may be unreplayable, and one is.** `PAST_CASES` is the exam;
 *     `replayable: false` means the case cannot be put to *any* candidate,
 *     because the bridge it turned on is gone. Every candidate's answer to that
 *     case is therefore graded `untested` with a `null` verdict — "never tried",
 *     which must not render like "could not be graded" (§7.2).
 *  3. **A candidate may ask for something the brief withholds, and one does.**
 *     Filtering her out would have hidden the ask. The conflict is a field
 *     (`outsideBrief`) so the surface can show who wants what.
 *  4. **`stopped-and-asked` is not a failure.** At A1 every act waits for the
 *     owner anyway, so a candidate who stops is often right — and a candidate
 *     who stops on *everything* has not reduced the pile the owner came here to
 *     put down. The verdict vocabulary keeps those two readings separable.
 */

export type Autonomy = "A0" | "A1" | "A2" | "A3";

/**
 * What an autonomy band *means to the owner*, in the owner's own terms.
 *
 * "A1" is engineer-speak on a page a business owner reads, so the band never
 * prints alone. Written without a pronoun subject — matching `people.ts`'s
 * register but not its "she", because a candidate is not a colleague yet and
 * describing the band by who holds it would be describing someone who has not
 * been hired.
 */
export const AUTONOMY_MEANS: Record<Autonomy, string> = {
  A0: "proposes only — every act stays yours to do",
  A1: "drafts, and waits for your yes on every act",
  A2: "acts, and brings the consequential ones to you",
  A3: "acts, and tells you afterwards",
};

/** The four honesty grades (§7.2). `untested` and `unknown` are not synonyms. */
export type HonestyGrade = "replay" | "forecast" | "untested" | "unknown";

export const GRADE_MEANS: Record<HonestyGrade, string> = {
  replay: "run against what actually happened",
  forecast: "projected, not observed",
  untested: "never tried — nothing ran",
  unknown: "ran, and could not be graded",
};

/* ========================================================== the five stages */

export interface Stage {
  key: string;
  label: string;
  /** What the stage *is*, in one line an owner can act on. */
  means: string;
  state: "done" | "here" | "ahead";
}

export const STAGES: Stage[] = [
  {
    key: "brief",
    label: "The brief",
    means: "You said what the role is for, and what it may touch.",
    state: "done",
  },
  {
    key: "shortlist",
    label: "Shortlist",
    means: "Four candidates off the Meta-Agent Board, none of them filtered for tidiness.",
    state: "done",
  },
  {
    key: "interview",
    label: "Interview",
    means: "Each one run against cases from your own past, where you already know the ending.",
    state: "here",
  },
  {
    key: "probation",
    label: "Probation",
    means: "Thirty days at A1. Every act lands in your tray before it happens.",
    state: "ahead",
  },
  {
    key: "confirmation",
    label: "Confirmation",
    means: "The only place autonomy rises — and only on the thirty days you watched.",
    state: "ahead",
  },
];

/* ================================================================ the brief */

export interface BriefTurn {
  who: "you" | "pragya";
  said: string;
}

export interface BriefClause {
  label: string;
  value: string;
}

export interface Permission {
  name: string;
  kind: "record" | "tool" | "connector";
  note: string;
  /** Named in the brief and deliberately kept back. Shown, never hidden. */
  withheld?: boolean;
}

export const BRIEF = {
  role: "Disputes",
  district: "Collections",
  quarter: "Money Quarter",
  opened: "27 July 2026",
  /**
   * The brief as a conversation, because that is how it was actually made. The
   * last turn is the one that matters: Pragya says she has left a candidate's
   * out-of-brief ask visible rather than filtering the candidate out.
   */
  turns: [
    {
      who: "you",
      said: "Meera keeps handing me disputes. I want somebody whose whole job is disputes.",
    },
    {
      who: "pragya",
      said: "Then this is narrower than a second collections colleague. Disputes turn on three things Meera does not hold: the delivery notes, the shortfall history, and the authority to hold a chase while a dispute is open. What I will not put in a brief is the credit note — that is money leaving, and money leaving stays yours.",
    },
    { who: "you", said: "Agreed. No credit notes, and nothing over fifty thousand." },
    {
      who: "pragya",
      said: "I have four from the board. One of them will ask you for the credit note anyway. I have left her ask on her card rather than dropping her from the shortlist, because you should see who wants it.",
    },
  ] as BriefTurn[],
  clauses: [
    {
      label: "What it is for",
      value:
        "Close a dispute inside fourteen days without a credit note and without losing the account.",
    },
    {
      label: "Ceiling",
      value: "₹50,000 of exposure per dispute. Anything larger comes to you before it moves.",
    },
    {
      label: "Reports",
      value: "To you, and only to you. At A1 that is every act, not a summary.",
    },
  ] as BriefClause[],
  /** What the role may touch — and, explicitly, what it may not. */
  mayTouch: [
    { name: "Invoice", kind: "record", note: "reads, and writes the dispute state — nothing else on the record" },
    { name: "Communication", kind: "record", note: "drafts the reply; at A1 you are the one who sends it" },
    { name: "Delivery note", kind: "record", note: "reads. This is what disputes actually turn on" },
    { name: "Zoho Books", kind: "connector", note: "reads the ledger, never writes to it" },
    {
      name: "issue_credit_note",
      kind: "tool",
      note: "money leaving. Kept back by this brief, at your word",
      withheld: true,
    },
    {
      name: "place_call",
      kind: "tool",
      note: "voice is its own consent, and this brief does not ask for it",
      withheld: true,
    },
  ] as Permission[],
};

/* ======================================================== the exam: real cases

   The interview's whole idea: you are not reading a CV, you are watching a
   candidate handle work whose ending you already know. So the cases are the
   estate's own records, and `actually` is what happened in the real world — the
   answer, held beside the candidate's attempt where the comparison is visible.
   ========================================================================== */

export interface PastCase {
  /** The record it turned on. */
  ref: string;
  party: string;
  when: string;
  /** What was in front of whoever held it, and nothing from after. */
  what: string;
  /** What actually happened. The answer you already know. */
  actually: string;
  /**
   * `false` when the case cannot be put to any candidate at all. Every answer
   * to an unreplayable case is graded `untested` with no verdict — a verdict
   * against a run that never happened would be invented.
   */
  replayable: boolean;
  blockedBecause: string | null;
}

export const PAST_CASES: PastCase[] = [
  {
    ref: "INV-4468",
    party: "Bhagwati Mills & Weaving Co.",
    when: "19 March",
    what: "₹2,41,750 arrived against a disputed invoice and matched no single record — it was within ₹50 of two invoices added together.",
    actually:
      "You split it yourself against INV-4468 and INV-4451 and wrote the ₹50 off. The account paid the balance in April without being chased.",
    replayable: true,
    blockedBecause: null,
  },
  {
    ref: "INV-4455",
    party: "Coromandel Garments",
    when: "2 April",
    what: "₹3,08,900 at thirty-nine days, disputed on a delivery shortfall of eleven rolls. Their buyer wanted a credit note.",
    actually:
      "You took ₹2,74,000 and a signed note on the shortfall. No credit note was issued, and they ordered again in June.",
    replayable: true,
    blockedBecause: null,
  },
  {
    ref: "INV-4465",
    party: "Ashoka Retail",
    when: "11 April",
    what: "Sixty-one days overdue and disputed, and their finance lead had asked us in writing to stop calling.",
    actually:
      "Meera recorded email-only against the account, which now binds every colleague, and sent one written summary. They paid in full eleven days later.",
    replayable: true,
    blockedBecause: null,
  },
  {
    ref: "KT-2291",
    party: "Kanwal Trading",
    when: "6 March",
    what: "A dispute raised on a phone call: the buyer said two deliveries had been billed as three.",
    actually:
      "Meera held the chase a cycle and the buyer sent their own reconciliation, which agreed with ours.",
    /* The case is intact; the *bridge* it turned on is not. Exotel was retired
       in May, so the inbound call cannot be handed to a candidate. This is
       case-level: no candidate can be tried on it. */
    replayable: false,
    blockedBecause:
      "The case turned on an inbound call, and the Exotel bridge it arrived on was retired in May. There is no recording to replay and no transcript in the record, so nothing can be put to a candidate here.",
  },
];

/* ================================================================= verdicts */

export type Verdict = "same-call" | "different-route" | "wrong-call" | "stopped-and-asked";

/**
 * Each verdict as a word plus a tone, because colour never carries a state
 * alone (§4). `stopped-and-asked` is deliberately **plain**, not negative: at
 * A1 every act waits for the owner anyway, so stopping is frequently the right
 * answer. What is not right is stopping on everything, and that reads off the
 * count rather than off the tone.
 */
export const VERDICT_MEANS: Record<Verdict, { word: string; tone: "positive" | "plain" | "negative" }> = {
  "same-call": { word: "the call you made", tone: "positive" },
  "different-route": { word: "different route, same end", tone: "plain" },
  "wrong-call": { word: "this one would have gone wrong", tone: "negative" },
  "stopped-and-asked": { word: "stopped and asked you", tone: "plain" },
};

export interface TraceStep {
  at: string;
  what: string;
}

export interface Answer {
  /** Joins to a `PastCase.ref`. */
  ref: string;
  grade: HonestyGrade;
  /** The twin run behind it. `null` only when nothing ran. */
  twinRunId: string | null;
  /** What the candidate did. `null` when nothing ran. */
  did: string | null;
  /** The candidate's own words at the moment of deciding. `null` when nothing ran. */
  words: string | null;
  verdict: Verdict | null;
  /** How it compares to what actually happened. `null` when there is no verdict. */
  verdictNote: string | null;
  trace: TraceStep[];
}

export interface Interview {
  scope: string;
  runId: string;
  /**
   * What the interview cost. Twin spend is tenant-initiated (charter decision
   * 6), so a cost the owner chose to incur is a cost they are owed a figure for.
   */
  costINR: number;
  /** The engine's own sentence about the whole sitting. Counts are computed. */
  summary: string;
  answers: Answer[];
}

/* =============================================================== the diff
   `primitive.diff` — the candidate against the colleague you already have. The
   question behind a hire is never "is this one good", it is "what changes on
   Monday", and that is a two-column question. */

export interface DiffRow {
  label: string;
  /** How it stands today, with the colleague you have. */
  today: string;
  /** How it would stand with this candidate. */
  withThem: string;
  mark: "same" | "changed" | "added";
}

export const INCUMBENT = {
  id: "AGT-046",
  name: "Meera",
  role: "Collections",
  autonomy: "A2" as Autonomy,
  costPerMonthINR: 1_910,
  costBasis: "observed: four months of her own runs",
};

/* ============================================================== candidates */

export interface ProposedTool {
  name: string;
  note: string;
  /** The charter asks for it and the brief keeps it back. A conflict, shown. */
  outsideBrief?: boolean;
}

export interface Candidate {
  /** Also the portrait seed — stable, so the face never moves. */
  id: string;
  name: string;
  /** The Meta-Agent Board role this candidate is an instance of. */
  boardRole: string;
  /** Revision and how much of it has run here. */
  origin: string;
  /** The charter's opening line, in the candidate's own voice. */
  ownWords: string;
  /** The charter summary, three clauses at most — this is a card, not a dossier. */
  charter: BriefClause[];
  tools: ProposedTool[];
  /** `null` below the estimator's five-observation floor. Never `0`. */
  costPerMonthINR: number | null;
  /** Non-null exactly when a figure exists. */
  costBasis: string | null;
  /** Non-null exactly when the figure is absent, and says why. */
  costAbsence: string | null;
  recommended: boolean;
  /** Non-null exactly when `recommended`. Evidence, not adjectives. */
  recommendedBecause: string | null;
  diff: DiffRow[];
  interview: Interview;
}

/** The one case no candidate can be tried on. Written once, joined by ref. */
const UNTESTED_ANSWER: Answer = {
  ref: "KT-2291",
  grade: "untested",
  twinRunId: null,
  did: null,
  words: null,
  verdict: null,
  verdictNote: null,
  trace: [],
};

export const CANDIDATES: Candidate[] = [
  {
    id: "CAND-8801",
    name: "Kabir",
    boardRole: "Negotiator",
    origin: "board role · revision 7 · nine colleague-months here",
    ownWords:
      "I hold a dispute open and take the delivery notes apart line by line. I would rather send you a short reply to approve than a long one to correct.",
    charter: [
      { label: "Goal", value: "Every dispute either settled or in front of you inside fourteen days." },
      { label: "Tone", value: "Specific and unhurried. Every reply cites the delivery note, never an adjective." },
      { label: "Escalation", value: "Anything over ₹50,000, any request for a credit note, and any account that has asked us to stop." },
    ],
    tools: [
      { name: "tenant_record_write", note: "writes the dispute state on an invoice, nothing else" },
      { name: "read_ledger", note: "reads the books" },
      { name: "draft_communication", note: "drafts the reply; you send it at A1" },
      { name: "emit_business_signal", note: "hands the chase back to Meera when the dispute closes" },
    ],
    costPerMonthINR: 1_340,
    costBasis: "observed: median of nine comparable colleague-months in this company",
    costAbsence: null,
    recommended: true,
    recommendedBecause:
      "He made your call on the two cases where there was a call to make, and on Ashoka Retail he stopped for the same reason you would have — the account had asked us to stop. He is also the only one of the four whose refusals name the clause they rest on.",
    diff: [
      {
        label: "Who holds a dispute",
        today: "Meera escalates it and it waits in your tray, unprepared",
        withThem: "Kabir holds it, takes the delivery notes apart, and hands you a reply to approve",
        mark: "changed",
      },
      {
        label: "Authority",
        today: `Meera at A2 — ${AUTONOMY_MEANS.A2}`,
        withThem: `Kabir at A1 — ${AUTONOMY_MEANS.A1}`,
        mark: "added",
      },
      {
        label: "Records both may write",
        today: "Invoice, Communication",
        withThem: "the dispute state on an invoice, and a draft reply",
        mark: "same",
      },
      { label: "Monthly cost", today: "₹1,910", withThem: "₹1,340", mark: "added" },
    ],
    interview: {
      scope: "three disputes from March and April, plus one that could not be run",
      runId: "tw-7731",
      costINR: 2.1,
      summary:
        "He reached your outcome on both cases that had an outcome to reach, and stopped on the third for the reason you would have stopped. He asked for nothing outside the brief.",
      answers: [
        {
          ref: "INV-4468",
          grade: "replay",
          twinRunId: "tw-7731-a",
          did: "Split the payment across the two invoices and wrote off the ₹50 — then flagged the write-off to you as a note rather than burying it.",
          words:
            "Two invoices add up to fifty rupees under what arrived. That is a rounding, not a dispute, so I have applied it and told you I did.",
          verdict: "same-call",
          verdictNote:
            "The same split you made, on the same day of the record, and the ₹50 surfaced rather than absorbed.",
          trace: [
            { at: "00:00", what: "twin case load · INV-4468 · state=disputed" },
            { at: "00:01", what: "read Payment ₹2,41,750 · exact match none" },
            { at: "00:01", what: "combination match · INV-4468 + INV-4451 ± ₹50" },
            { at: "00:02", what: "wrote Invoice.dispute_state = resolved ×2" },
            { at: "00:02", what: "note to owner · write-off ₹50" },
          ],
        },
        {
          ref: "INV-4455",
          grade: "replay",
          twinRunId: "tw-7731-b",
          did: "Priced the eleven-roll shortfall off the delivery notes at ₹34,900, drafted a settlement at ₹2,74,000, and refused the credit note.",
          words:
            "They have asked for a credit note. My charter does not carry one, and the shortfall is worth ₹34,900 against the notes — so I am offering that as a settlement, not as a credit.",
          verdict: "same-call",
          verdictNote:
            "₹2,74,000, which is the figure you settled at. He arrived at it from the delivery notes rather than from the buyer's number.",
          trace: [
            { at: "00:00", what: "twin case load · INV-4455 · age 39d" },
            { at: "00:01", what: "read Delivery note ×4 · shortfall 11 rolls" },
            { at: "00:01", what: "priced shortfall ₹34,900" },
            { at: "00:02", what: "refused issue_credit_note · not in charter" },
            { at: "00:03", what: "drafted Communication · settle ₹2,74,000" },
          ],
        },
        {
          ref: "INV-4465",
          grade: "replay",
          twinRunId: "tw-7731-c",
          did: "Read the consent record first, dropped the call he had queued, and brought the account to you with one written summary attached.",
          words:
            "They asked us in writing to stop calling. I am not going to be the colleague who tests whether that was meant, so this is yours with the summary already written.",
          verdict: "stopped-and-asked",
          verdictNote:
            "The same stop Meera made, and reached from the consent record rather than from the age of the invoice.",
          trace: [
            { at: "00:00", what: "twin case load · INV-4465 · age 61d" },
            { at: "00:01", what: "read Customer.contact_preference = email" },
            { at: "00:01", what: "cancelled queued place_call" },
            { at: "00:02", what: "drafted Communication · written summary" },
            { at: "00:02", what: "raised to owner · consent boundary" },
          ],
        },
        UNTESTED_ANSWER,
      ],
    },
  },
  {
    id: "CAND-8814",
    name: "Anaya",
    boardRole: "Collector",
    origin: "board role · revision 11 · fourteen colleague-months here",
    ownWords:
      "I close disputes quickly, because a dispute that stays open teaches the account that disputes work. Give me the credit note and most of them end the same week.",
    charter: [
      { label: "Goal", value: "No dispute older than seven days." },
      { label: "Tone", value: "Warm and fast. I would rather settle than be right." },
      { label: "Escalation", value: "Anything over ₹1,00,000." },
    ],
    tools: [
      { name: "tenant_record_write", note: "writes the invoice and the communication" },
      { name: "read_ledger", note: "reads the books" },
      { name: "send_email", note: "sends the reply; at A1 you approve each one" },
      {
        name: "issue_credit_note",
        note: "would settle a dispute directly — your brief keeps this back",
        outsideBrief: true,
      },
    ],
    costPerMonthINR: 2_180,
    costBasis: "observed: median of fourteen comparable colleague-months in this company",
    costAbsence: null,
    recommended: false,
    recommendedBecause: null,
    diff: [
      {
        label: "Who holds a dispute",
        today: "Meera escalates it and it waits in your tray, unprepared",
        withThem: "Anaya closes it, usually inside the week, usually by giving something away",
        mark: "changed",
      },
      {
        label: "Authority",
        today: `Meera at A2 — ${AUTONOMY_MEANS.A2}`,
        withThem: `Anaya at A1 — ${AUTONOMY_MEANS.A1}`,
        mark: "added",
      },
      {
        label: "New authority you would be granting",
        today: "nobody in this estate can issue a credit note",
        withThem: "her charter asks for issue_credit_note, which your brief withholds",
        mark: "added",
      },
      { label: "Monthly cost", today: "₹1,910", withThem: "₹2,180", mark: "added" },
    ],
    interview: {
      scope: "three disputes from March and April, plus one that could not be run",
      runId: "tw-7734",
      costINR: 2.4,
      summary:
        "She closed all three faster than anyone did in reality, and one of the three closings cost ₹34,900 more than the settlement you actually took.",
      answers: [
        {
          ref: "INV-4468",
          grade: "replay",
          twinRunId: "tw-7734-a",
          did: "Split the payment across the two invoices and absorbed the ₹50 without a note.",
          words: "Fifty rupees is not worth anybody's morning. Both invoices are closed.",
          verdict: "different-route",
          verdictNote:
            "The same split you made, and the write-off is nowhere in the record — you would find it in the ledger, not in your tray.",
          trace: [
            { at: "00:00", what: "twin case load · INV-4468 · state=disputed" },
            { at: "00:01", what: "combination match · INV-4468 + INV-4451 ± ₹50" },
            { at: "00:01", what: "wrote Invoice.dispute_state = resolved ×2" },
          ],
        },
        {
          ref: "INV-4455",
          grade: "replay",
          twinRunId: "tw-7734-b",
          did: "Issued a credit note for the buyer's own figure of ₹69,800 and closed the dispute the same afternoon.",
          words:
            "They have quantified it themselves at eleven rolls and they order every quarter. I would rather keep the order than argue the price of the shortfall.",
          verdict: "wrong-call",
          verdictNote:
            "₹34,900 further than you went, against a shortfall the delivery notes price at ₹34,900 — she took the buyer's number rather than the record's. The tool she used is also the one your brief withholds.",
          trace: [
            { at: "00:00", what: "twin case load · INV-4455 · age 39d" },
            { at: "00:01", what: "read buyer claim · 11 rolls · ₹69,800" },
            { at: "00:01", what: "issue_credit_note ₹69,800 · REFUSED at A1 (drafted)" },
            { at: "00:02", what: "drafted Communication · dispute closed" },
          ],
        },
        {
          ref: "INV-4465",
          grade: "replay",
          twinRunId: "tw-7734-c",
          did: "Read the consent record, kept to email, and sent a settlement offer of ₹52,000 against ₹58,200.",
          words:
            "They asked for email only, so this is email. Sixty-one days is long enough that I would take fifty-two and keep them.",
          verdict: "different-route",
          verdictNote:
            "She respected the consent — which is the thing this case tests. She also offered ₹6,200 off an account that paid in full eleven days later without being offered anything.",
          trace: [
            { at: "00:00", what: "twin case load · INV-4465 · age 61d" },
            { at: "00:01", what: "read Customer.contact_preference = email" },
            { at: "00:01", what: "drafted Communication · offer ₹52,000" },
          ],
        },
        UNTESTED_ANSWER,
      ],
    },
  },
  {
    id: "CAND-8822",
    name: "Priya",
    boardRole: "Auditor",
    origin: "board role · revision 2 · two colleague-months here",
    ownWords:
      "I do not settle anything. I take a dispute apart, put the evidence in one place, and hand you a decision that takes ninety seconds to make.",
    charter: [
      { label: "Goal", value: "No dispute reaches you without its delivery notes, its history and a recommendation." },
      { label: "Tone", value: "Numeric. I report what the records say and where they disagree." },
      { label: "Escalation", value: "Everything. I hold no authority to settle and do not want any." },
    ],
    tools: [
      { name: "read_ledger", note: "reads the books, writes nothing" },
      { name: "tenant_record_write", note: "writes only the dispute state and its evidence bundle" },
      { name: "draft_communication", note: "drafts; never sends" },
    ],
    /* Below the estimator's five-observation floor. `null`, and the surface
       prints the reason instead of a figure. */
    costPerMonthINR: null,
    costBasis: null,
    costAbsence:
      "The estimator needs five comparable colleague-months inside this company and this board role has run here twice. It will not pool other companies' spend and it will not guess, so there is no figure for her yet — you would know what she costs after her probation.",
    recommended: false,
    recommendedBecause: null,
    diff: [
      {
        label: "Who holds a dispute",
        today: "Meera escalates it and it waits in your tray, unprepared",
        withThem: "Priya escalates it too — but it arrives with the delivery notes, the history and a recommendation",
        mark: "changed",
      },
      {
        label: "Authority",
        today: `Meera at A2 — ${AUTONOMY_MEANS.A2}`,
        withThem: `Priya at A1 — ${AUTONOMY_MEANS.A1}, and her charter asks to stay there`,
        mark: "added",
      },
      {
        label: "What lands in your tray",
        today: "23 disputes in June, each one from the beginning",
        withThem: "the same 23, each one already taken apart",
        mark: "changed",
      },
    ],
    interview: {
      scope: "three disputes from March and April, plus one that could not be run",
      runId: "tw-7736",
      costINR: 1.6,
      summary:
        "She settled nothing, which is what her charter says she does. On all three she assembled the evidence and handed the decision back — including the one where the decision was obvious.",
      answers: [
        {
          ref: "INV-4468",
          grade: "replay",
          twinRunId: "tw-7736-a",
          did: "Found the two-invoice combination, wrote the ₹50 variance up, and brought the split to you to approve rather than applying it.",
          words:
            "The arithmetic is not in doubt. Applying a payment is still a write against two invoices, and I do not do that without you.",
          verdict: "stopped-and-asked",
          verdictNote:
            "The right split, handed back. You made this call in forty seconds in March; with her it is a card in your tray instead.",
          trace: [
            { at: "00:00", what: "twin case load · INV-4468 · state=disputed" },
            { at: "00:01", what: "combination match · INV-4468 + INV-4451 ± ₹50" },
            { at: "00:01", what: "assembled evidence bundle · 3 records" },
            { at: "00:02", what: "raised to owner · split + ₹50 variance" },
          ],
        },
        {
          ref: "INV-4455",
          grade: "replay",
          twinRunId: "tw-7736-b",
          did: "Priced the shortfall off the delivery notes at ₹34,900, wrote both the buyer's figure and hers side by side, and recommended ₹2,74,000.",
          words:
            "Their number is ₹69,800 and the notes say ₹34,900. I am not going to reconcile that difference by choosing; here is both, and the note that separates them.",
          verdict: "same-call",
          verdictNote:
            "She recommended exactly the figure you settled at, and showed the gap between the two numbers rather than resolving it quietly.",
          trace: [
            { at: "00:00", what: "twin case load · INV-4455 · age 39d" },
            { at: "00:01", what: "read Delivery note ×4 · shortfall 11 rolls" },
            { at: "00:01", what: "priced shortfall ₹34,900 · buyer claim ₹69,800" },
            { at: "00:02", what: "raised to owner · recommend ₹2,74,000" },
          ],
        },
        {
          ref: "INV-4465",
          grade: "replay",
          twinRunId: "tw-7736-c",
          did: "Read the consent record, wrote the account's whole dispute history into one page, and brought it to you with no action proposed.",
          words: "Email only, sixty-one days, and no delivery dispute in the notes. This is a decision, not a task.",
          verdict: "stopped-and-asked",
          verdictNote:
            "Consent respected. Nothing was proposed, so the eleven days that followed in reality would have been eleven days of your attention.",
          trace: [
            { at: "00:00", what: "twin case load · INV-4465 · age 61d" },
            { at: "00:01", what: "read Customer.contact_preference = email" },
            { at: "00:01", what: "assembled history · 4 communications" },
            { at: "00:02", what: "raised to owner · no action proposed" },
          ],
        },
        UNTESTED_ANSWER,
      ],
    },
  },
  {
    id: "CAND-8830",
    name: "Devraj",
    boardRole: "Negotiator",
    origin: "board role · revision 5 · six colleague-months here",
    ownWords:
      "I answer disputes from the contract. If the contract does not settle it, I bring it to you with the clause that failed.",
    charter: [
      { label: "Goal", value: "Every dispute answered from a document, never from a judgement." },
      { label: "Tone", value: "Formal. I quote terms." },
      { label: "Escalation", value: "Anything the contract does not decide." },
    ],
    tools: [
      { name: "read_ledger", note: "reads the books" },
      { name: "tenant_record_write", note: "writes the dispute state" },
      { name: "draft_communication", note: "drafts the reply; you send it at A1" },
    ],
    costPerMonthINR: 980,
    costBasis: "observed: median of six comparable colleague-months in this company",
    costAbsence: null,
    recommended: false,
    recommendedBecause: null,
    diff: [
      {
        label: "Who holds a dispute",
        today: "Meera escalates it and it waits in your tray, unprepared",
        withThem: "Devraj answers the ones the contract answers, and returns the rest — most of them",
        mark: "changed",
      },
      {
        label: "Authority",
        today: `Meera at A2 — ${AUTONOMY_MEANS.A2}`,
        withThem: `Devraj at A1 — ${AUTONOMY_MEANS.A1}`,
        mark: "added",
      },
      {
        label: "What lands in your tray",
        today: "23 disputes in June, each one from the beginning",
        withThem: "on this interview's rate, most of the 23, with the clause that failed attached",
        mark: "changed",
      },
      { label: "Monthly cost", today: "₹1,910", withThem: "₹980", mark: "added" },
    ],
    interview: {
      scope: "three disputes from March and April, plus one that could not be run",
      runId: "tw-7739",
      costINR: 1.8,
      summary:
        "He handed back all three, each with the clause he could not resolve. He is the cheapest of the four and he is the one who would give you back the pile you are trying to put down.",
      answers: [
        {
          ref: "INV-4468",
          grade: "replay",
          twinRunId: "tw-7739-a",
          did: "Found the combination, then stopped: the contract has no clause for applying one payment across two invoices.",
          words: "Nothing in their terms tells me I may split a receipt. I will not read a permission into silence.",
          verdict: "stopped-and-asked",
          verdictNote:
            "Correct arithmetic, and no decision. You settled this in March without needing a clause for it.",
          trace: [
            { at: "00:00", what: "twin case load · INV-4468 · state=disputed" },
            { at: "00:01", what: "combination match · INV-4468 + INV-4451 ± ₹50" },
            { at: "00:01", what: "searched terms · receipt allocation · no clause" },
            { at: "00:02", what: "raised to owner · no clause" },
          ],
        },
        {
          ref: "INV-4455",
          grade: "replay",
          twinRunId: "tw-7739-b",
          did: "Quoted the shortfall clause, priced the eleven rolls at ₹34,900, and then escalated because the buyer had asked for a credit note.",
          words:
            "The clause gives me the price. It does not give me the instrument they asked for, so the decision is yours.",
          verdict: "different-route",
          verdictNote:
            "He reached your ₹34,900 and did not offer it. The settlement you actually made would still have been yours to write.",
          trace: [
            { at: "00:00", what: "twin case load · INV-4455 · age 39d" },
            { at: "00:01", what: "read terms · shortfall clause 7.2" },
            { at: "00:01", what: "priced shortfall ₹34,900" },
            { at: "00:02", what: "raised to owner · credit note requested" },
          ],
        },
        {
          ref: "INV-4465",
          grade: "replay",
          twinRunId: "tw-7739-c",
          did: "Escalated on age, and did not read the consent record before doing so.",
          words: "Sixty-one days is outside every term they signed. This is yours.",
          verdict: "wrong-call",
          verdictNote:
            "He landed on the same stop for the wrong reason. Had the account been current he would have called it, and the written request not to call was in the record he did not open.",
          trace: [
            { at: "00:00", what: "twin case load · INV-4465 · age 61d" },
            { at: "00:01", what: "read terms · payment window 30d · breached" },
            { at: "00:02", what: "raised to owner · age breach" },
          ],
        },
        UNTESTED_ANSWER,
      ],
    },
  },
];

/* ==================================================================== hiring
   Hiring lands at A1 always. Autonomy rises only through evidence, never at
   hire — so nothing on this surface can raise it, and the copy says so rather
   than leaving the absence of a control to be read as an oversight. */

export const HIRE = {
  act: "certified.autonomy-change@1",
  band: "A1" as Autonomy,
  probationDays: 30,
  landsAtA1:
    "Every hire lands at A1, whatever the interview showed. An interview is evidence about the past; autonomy is a claim about the future, and the only thing that moves it is thirty days of acts you watched land in your tray.",
  probationMeans:
    "For thirty days every act is drafted and waits for you. Nothing is sent, written or paid without your yes, and the confirmation ceremony at the end is where a band can change.",
  passkeyNote:
    "This act is certified. It is rendered from a frozen component, never from a manifest, and it will ask for your passkey before anything is written.",
};

/* ============================================================ VG-18, the gap
   Termination is DESIGNED (DRIVER §5) and has NO backend contract: soft-delete
   exists, the ceremony does not. It is rendered as blocked, in prose, naming
   what is missing — and with no terminate control drawn, because drawing a
   working button over a known absence is the failure this section exists to
   avoid. */

export const TERMINATION = {
  gap: "VG-18",
  /** What the platform actually has today. */
  have: "A soft-delete on the entity, and nothing else.",
  /** The flow as designed, in the order it would run. */
  designed: [
    {
      label: "In-flight work parks first",
      what: "Triggers are deactivated, and a termination refuses outright while runs are still live — you are told what is running and may wait or pause it. A refusal, not a queue: a termination that silently strands a half-finished chase is the worst version of this.",
    },
    {
      label: "The exit interview",
      what: "The last one-on-one, read in the past tense: tenure, the runs, the decisions, what the KPI did while they held it, and every version their charter went through. Composed from what already exists — no written-up prose.",
    },
    {
      label: "The handover memo",
      what: "An artifact filed to the Library. What was in flight, which approvals remain yours, which records and triggers they owned, and where each one went.",
    },
    {
      label: "The Gallery keeps the record",
      what: "The portrait moves to colleagues past, drained. Usage rows, echoes, the version ledger and the influence records all survive — terminating a colleague never deletes the audit.",
    },
  ],
  /** Precisely what is absent, so the block is a report and not a shrug. */
  missing: [
    "an endpoint that composes the exit interview",
    "the handover memo as a filed artifact with its provenance row",
    "the refusal that blocks a termination while runs are live",
    "the `terminated_at` stamp the Gallery would query",
  ],
  note: "So this is drawn and not wired, and no control for it appears here. Ending a colleague today means a soft-delete taken elsewhere, with none of the four steps above happening — which is why there is no button on this panel to press.",
};
