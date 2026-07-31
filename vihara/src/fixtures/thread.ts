/**
 * The Thread's fixtures (D6 §16–18, R-3c §3.1).
 *
 * One day of Pragya's thread, shaped to the D5 contracts so R-4 is a swap of the
 * data source: turns come from `pragya/channel`, the story cards' figures from
 * `narrative.story-card@1`'s own bindings, and the step-up from
 * `certified.step-up@1`.
 *
 * Two rules govern the content.
 *
 * **It is the same Thursday the desk is having.** Every id, party and figure
 * here agrees with `fixtures/estate.ts` and `fixtures/decisions.ts` — Meera's
 * release is HITL-8841, Anjali's reminder is HITL-8839, days-sales-outstanding
 * is 38 from 41. The Line and the desk disagreeing about the estate is the one
 * failure a person notices immediately and never forgives, and fixtures are
 * where that divergence starts.
 *
 * **It is realistic and awkward.** Long counterparties, a receivable 47 days
 * past due, a probationer whose second reversal lands two days before his
 * probation ends, and one story whose figure does not exist — because the KPI
 * series starts 2026-07-25 with no backfill and there is no earlier week to
 * compare against (DESIGN_CONTRACT §7.3).
 */

/** The day the thread covers. Matches `STANDUP_DAY` in `fixtures/decisions.ts`. */
export const THREAD_DAY = { label: "Thursday 30 July" };

interface TurnBase {
  id: string;
  /** Local wall time, the tenant's own — `COMPANY.localHour` is 21. */
  at: string;
}

/** A line she wrote. The thread's ground state, and deliberately not a card:
 *  most of what she says does not need an object drawn around it. */
export interface ThreadNote extends TurnBase {
  kind: "note";
  text: string;
}

/**
 * A line she spoke. `seconds` is the length of the recording as the channel
 * reported it — never derived from anything on the client.
 *
 * There is no audio binding on this turn, and that is the shape of the product
 * rather than an omission: the morning job pre-generates her voice for the
 * Morning Story (R-3c §3.2), while the thread carries the transcript, which is
 * what a person standing in a shop can actually consume.
 */
export interface ThreadVoice extends TurnBase {
  kind: "voice";
  seconds: number;
  text: string;
}

/**
 * `narrative.story-card@1`. `title` and `template` are its two props; `figure`
 * is whatever the card's binding — `kpi.current`, `records.aggregate`,
 * `runs.history` or `approval.detail` — resolved to. Which of the four it was
 * is not carried here: C never draws a binding source, and a field kept for a
 * surface that will not render it is a shape invented on spec.
 *
 * **`figure: null` means the source produced nothing, and the card then renders
 * no figure at all** — not a zero, not a dash, not "unknown" (DESIGN_CONTRACT
 * §7.1). The template is written so that it still stands up alone, because a
 * sentence that only parses once a number is dropped into it is a sentence that
 * will one day be read with a hole in it.
 */
export interface ThreadStory extends TurnBase {
  kind: "story";
  title: string;
  template: string;
  figure: { value: string; label: string } | null;
}

export type ThreadTurn = ThreadNote | ThreadVoice | ThreadStory;

/** Oldest first, as the history endpoint returns it. The surface decides which
 *  way to read it; the fixture does not pre-sort for a layout. */
export const THREAD: ThreadTurn[] = [
  {
    id: "TH-1",
    kind: "voice",
    at: "06:58",
    seconds: 41,
    text: "Good morning. I have read everything that came in overnight, and two things will want you today — neither of them before noon. Meera is holding a release to Sundar Textiles, and Anjali has stopped at the third reminder to Kanwal Trading, because the third one is where the language stops being polite and she may not change tone on her own.",
  },
  {
    id: "TH-2",
    kind: "note",
    at: "09:20",
    text: "Farhan caught a duplicate against Bhagwati Mills & Weaving Co. before it reached the ledger — ₹41,600, posted twice by the same upload. There is nothing for you to do. I am telling you because it is the third duplicate to arrive down that route this month, and the fourth is the one I would want to talk about.",
  },
  {
    id: "TH-3",
    kind: "story",
    at: "11:05",
    title: "Collections pulled back three days",
    template:
      "Meera closed eleven of the fourteen chases she picked up, and days sales outstanding came back to thirty-eight from forty-one. It is still eight days past where you want it, and almost all of that gap sits in four accounts.",
    figure: { value: "38d", label: "days sales outstanding · target 30" },
  },
  {
    id: "TH-4",
    kind: "story",
    at: "14:32",
    title: "Kanwal Trading has not answered in forty-seven days",
    template:
      "Two reminders have gone out and neither was answered. Anjali has drafted the third and it is waiting on you above. If you would rather ring them than send it, the number on file was last used in March and I cannot tell you whether it still reaches anyone.",
    figure: { value: "₹96,500", label: "overdue · KT-2291 · 47 days" },
  },
  {
    id: "TH-5",
    kind: "story",
    at: "17:12",
    title: "Week on week, I cannot tell you yet",
    /* The figure this card would carry does not exist: the KPI series starts on
       2026-07-25 with no backfill, so there is no earlier week to divide by. She
       says so in the template rather than the card drawing a dash, because a
       dash is a number-shaped hole and a person reads it as zero. */
    template:
      "On Monday you asked me to tell you each week whether the estate did better than the week before. I cannot yet. The measurements only begin on the twenty-fifth of July, so there is no earlier week to set this one against, and I would rather say that than draw you a line I made up. The first honest comparison is Friday next week.",
    figure: null,
  },
  {
    id: "TH-6",
    kind: "voice",
    at: "19:40",
    seconds: 26,
    text: "One more thing before you put the phone down. Ravi reversed two postings this week, both of them across the quarter boundary, and his probation ends on Friday. I am not asking you to decide anything tonight. I am saying it now so that Friday is not the first time you hear it.",
  },
  {
    id: "TH-7",
    kind: "note",
    at: "20:55",
    text: "Devika had nothing to quote today. Vasudha Handloom Cooperative Ltd asked for a revised price on Tuesday and I have not let her answer it, because the request widens the quote from one buying entity to the whole group, and that is a scope you have not set.",
  },
];

/*
 * `STEP_UP` stood here: `certified.step-up@1` keyed by the tray card whose gold
 * path it authorised, carrying a `tier` and a `command_ref`.
 *
 * It is gone because R-4 part W gave one of those fields a source and proved
 * the other has none. The tier is on the wire — `certified.tier`, struck by
 * `genui/trays.py` from the same classification the gate itself runs — so
 * `ThreadSurface` reads it there, off the act it is actually standing under.
 * The reference is minted by the server at the moment it refuses
 * (`enforce_tier(..., command_ref=f"approval:{approval_id}")`) and printed by
 * the ceremony that was refused with it; nothing carries one before that. This
 * table's own note said a ref invented on the client would let one command's
 * confirmation authorise another — and a fixture ref keyed by a fixture id,
 * looked up with a real approval id, would simply never match, which is a
 * security control that quietly stops appearing. Both failures are worse than
 * printing no reference on a bar that is not the ceremony.
 */
