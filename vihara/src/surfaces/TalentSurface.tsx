import { useState } from "react";
import { Icon } from "../components/Icon";
import { Portrait } from "../components/Portrait";
import { artKeyFor, type EntityOut } from "../api/entities";
import {
  absentIn,
  fetchBriefs,
  fetchPastCases,
  type Brief,
  type BriefView,
  type PastCase,
  type PastCasesView,
} from "../api/talentBrief";
import {
  fetchEntities,
  parseTerminationRefusal,
  terminateColleague,
  type TerminationDone,
  type TerminationRefusal,
} from "../api/talent";
import { Bar, Empty, Failed, Lines, Scaffold, useChoice, useResource } from "../lifecycle";
import "./talent.css";

/**
 * The Talent Office · depth 2 · S (D6 §9) — on `GET /ai/talent/brief` and
 * `GET /ai/talent/past-cases` (R-4 part W; the two reads are D8's E4).
 *
 * **This surface is the payoff of E4, and E4's discipline is the design.** Both
 * endpoints ship an `absent` list travelling with the payload, naming per field
 * what the platform cannot answer and why. **Nine fields are on those two lists
 * and all nine are rendered here as absences, in the place the thing would have
 * been, in the endpoint's own words** — the same rule `DossierSurface` follows
 * for E3's seven. A talent office with the conversation quietly missing looks
 * like a brief nobody discussed. One that says *"`pragya_turns` is one flat
 * per-company stream — nothing marks a run of turns as this brief"* has told the
 * owner something true about their platform.
 *
 * ## What the wiring cost, and it is worth naming
 *
 * **The shortlist and the interview have no source at all, and they were two of
 * the three columns.** `brief_read._board_run` projects the Meta-Agent board
 * run's id, status and timings and *deliberately refuses to project its output*
 * — "guessing at candidates from a result blob is exactly the invention this
 * endpoint refuses" — and `past_cases` lists `answers` as absent because
 * "`twin_runs` holds scenario runs, which are not per-candidate-per-case, and
 * nothing joins a candidate to a case". So there are no candidates to compare,
 * no proposed charters, no per-candidate cost, and no verdicts.
 *
 * The three-column skeleton is kept and its materials are untouched; what
 * changed is what stands in the third column. The brief is column one, the exam
 * — which is entirely real — takes the wide middle, and column three carries the
 * shortlist gap in prose plus the act that *is* now wired. Redrawing those
 * cards against invented candidates was the one option not available.
 *
 * ## The gap that closed, and how it is drawn
 *
 * Termination was drawn blocked over four "missing" bullets, and **all four are
 * now false**: `POST /ai/talent/colleagues/{id}/terminate` shipped, refuses with
 * a 409 while runs are live and names them, files the handover memo as an
 * Artifact, and stamps `metadata_extensions["termination"]` before the
 * soft-delete so the Gallery's roster is a query. Verified against the live app
 * (the route answers) and against the database (four integration tests in
 * `backend/tests/integration/test_talent_termination_db.py`), not by compiling.
 * So the gap block is gone and a real control stands where it was.
 *
 * **That control is deliberately not certified, and this is the surface where
 * that claim gets settled.** `talent/router.py` says it in its own docstring:
 * termination is *"a plain governed act by owner decision (11_driver.md §2.3):
 * stopping a colleague must never be harder than hiring one, so there is no
 * `enforce_*` call here — deliberately"*. There is accordingly no
 * `certified.termination` row in `components/certified/acts.ts` and
 * `RunnableCertifiedType` is a closed set, so `useCertifiedAct` cannot be handed
 * one. Drawing a seal and promising a passkey over a path that will never ask
 * for one is precisely the fraud part C §6 calls the *dangerous* case — a
 * certified control that completes without a ceremony teaches the owner the
 * ceremony is decorative. It is therefore a plain button with a real confirm
 * step, no gold, and the 409 refusal rendered as the answer it is.
 *
 * **And nothing else on this surface is certified either.** The hire block was
 * the room's only gold and it was mislabelled: `acts.ts` records that hiring is
 * absent from the certified table on purpose, because `POST /ai/entities`
 * carries no `enforce_*` and only a *raise* is gated. With no shortlist there is
 * nobody to hire, so the block is gone rather than restated — and its one true
 * sentence, that autonomy moves on thirty watched days and never at hire,
 * survives in the shortlist gap.
 *
 * Density: still the operator view. The novice variant would collapse the exam
 * to the replayable count and the absences to one line with a disclosure.
 */

/**
 * The five stages, as designed. Copy rather than data, and it has to be: a
 * `capability_build` delegation's `stage` is the *onboarding* stage as an
 * integer, not a position in this flow, and reading one as the other would put a
 * "you are here" on evidence that says nothing of the kind.
 *
 * Only the first two can be evidenced at all — a brief exists, and a board run
 * either dispatched or did not. The last three are marked ahead always, and the
 * note under the rail says why rather than leaving five confident boxes.
 */
const STAGES: { key: string; label: string; means: string }[] = [
  {
    key: "brief",
    label: "The brief",
    means: "You said what the role is for. What the platform keeps of that is the subject and Pragya's promise.",
  },
  {
    key: "shortlist",
    label: "Shortlist",
    means: "The brief goes to the Meta-Agent board. The run is recorded; what it produced is not read back here.",
  },
  {
    key: "interview",
    label: "Interview",
    means: "A scoped twin session against work you already know the ending of. No such session is run anywhere yet.",
  },
  {
    key: "probation",
    label: "Thirty days",
    means: "Every act drafted and waiting on you, watched. Autonomy moves here or nowhere.",
  },
  {
    key: "confirmation",
    label: "Confirmation",
    means: "The band can change, on evidence you watched land in your own tray.",
  },
];

/** Stable empty: a fresh `[]` per render hands `useChoice` a new identity for
 *  no change on screen. */
const NO_BRIEFS: readonly Brief[] = [];

/** A gateway is an AGENT tagged `channel:*` — the estate's own predicate,
 *  copied from the dossier's roster rather than re-invented, so the two lists
 *  hold the same set of colleagues. */
function isGateway(entity: EntityOut): boolean {
  const tags = entity["tags"];
  return (
    Array.isArray(tags) &&
    tags.some((tag) => typeof tag === "string" && tag.startsWith("channel:"))
  );
}

function nameOf(entity: EntityOut): string {
  return entity.display_name !== null && entity.display_name !== ""
    ? entity.display_name
    : entity.name;
}

/** An ISO stamp as a person reads it. Never a fallback string: a caller with no
 *  stamp renders no line at all. */
function when(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  return at.toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function TalentSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const briefs = useResource(fetchBriefs);
  const cases = useResource(fetchPastCases);

  if (briefs.phase === "pending" || cases.phase === "pending") {
    return <TalentScaffold />;
  }

  if (briefs.phase === "failed") {
    return (
      <section className="ta">
        <Failed
          what="the hiring briefs"
          reason={briefs.reason}
          onRetry={briefs.retry}
        />
      </section>
    );
  }

  return (
    <Office
      briefs={briefs.value}
      cases={cases.phase === "ready" ? cases.value : null}
      casesFailure={cases.phase === "failed" ? cases : null}
      onEcho={onEcho}
    />
  );
}

function Office({
  briefs,
  cases,
  casesFailure,
  onEcho,
}: {
  briefs: BriefView;
  cases: PastCasesView | null;
  casesFailure: { reason: string; retry: () => void } | null;
  onEcho: (msg: string) => void;
}) {
  const list = briefs.briefs.length > 0 ? briefs.briefs : NO_BRIEFS;
  /* L1. The office opens on the newest brief, which the endpoint already
     returns first — derived, never an index asserted into state, because a
     tenant who has never asked for a colleague is the ordinary state of this
     room on the day it is installed. */
  const { chosen, chosenId, choose } = useChoice(list, (b) => b.brief_id);

  return (
    <section className="ta">
      {/* ================================================================ head */}
      <header className="ta-head">
        <div className="ta-head-top">
          <div>
            <span className="t-eyebrow">THE TALENT OFFICE</span>
            <h1 className="ta-title t-display">
              {/* The subject is what the owner asked for, in their own words as
                  Pragya recorded them. A brief whose params carried none prints
                  the room's name instead of a guessed job title. */}
              {chosen?.subject !== undefined && chosen.subject !== null
                ? `Hiring: ${chosen.subject}`
                : "Hiring a colleague"}
            </h1>
            <p className="ta-lead">
              A colleague is hired the way a person is — a brief, a shortlist, an
              interview, thirty days, and then a decision. What this room can show
              you today is the brief you gave and the work your estate has actually
              handled; where a step is not recorded anywhere, it says so instead of
              drawing one.
            </p>
          </div>
          <div className="ta-head-meta">
            <span className="m-chip">
              <Icon name="colleague" size={12} />
              {list.length} brief{list.length === 1 ? "" : "s"}
            </span>
            {chosen !== undefined && (
              <>
                <span className="m-chip">{chosen.status}</span>
                <span className="m-chip">opened {when(chosen.opened_at)}</span>
              </>
            )}
          </div>
        </div>

        {/* The five stages, each with what it means. No gold: a recommendation
            is neither "this needs you" nor "this is certified". */}
        <ol className="ta-stages">
          {STAGES.map((s) => (
            <li
              className="ta-stage"
              key={s.key}
              data-state={stateOf(s.key, chosen)}
            >
              <span className="ta-stage-top">
                <span className="ta-stage-mark" aria-hidden="true" />
                <span className="ta-stage-label">{s.label}</span>
                {stateOf(s.key, chosen) === "here" && (
                  <span className="ta-stage-here t-mono">you are here</span>
                )}
              </span>
              <span className="ta-stage-means">{s.means}</span>
            </li>
          ))}
        </ol>
        <p className="ta-note">
          Only the first two stages can be evidenced: a brief exists, and the
          board run either dispatched or did not.{" "}
          <strong>Nothing on the platform records a position in the last three</strong>
          , so none of them is ever marked, and a brief that has in fact reached
          probation would look no different from here.
        </p>
      </header>

      <div className="ta-cols">
        {/* ========================================================= the brief */}
        <div className="ta-col">
          <div className="ta-col-head">
            <h2 className="t-eyebrow">THE BRIEF</h2>
            <span className="ta-col-note t-mono">what was asked for, and when</span>
          </div>

          <div className="ta-col-scroll">
            {chosen === undefined ? (
              /* L2. A tenant who has never asked Pragya for a capability they
                 do not have has no brief, and that is a working room rather
                 than a broken one. */
              <Empty
                icon="colleague"
                title="You have not asked for a colleague yet."
                body="A brief starts when you tell Pragya you need something the estate cannot do. She records what you asked for and what she promised about it, and puts it to the Meta-Agent board. Nothing has been asked for on this account."
                note="capability_build delegations · none on record"
              />
            ) : (
              <>
                {list.length > 1 && (
                  <nav className="ta-brief-list" aria-label="Briefs">
                    {list.map((b) => (
                      <button
                        key={b.brief_id}
                        className="ta-brief-pick"
                        data-selected={b.brief_id === chosenId || undefined}
                        onClick={() => choose(b.brief_id)}
                      >
                        <span className="ta-brief-pick-subject">
                          {b.subject ?? "no subject recorded"}
                        </span>
                        <span className="t-mono ta-brief-pick-when">
                          {when(b.opened_at)}
                        </span>
                      </button>
                    ))}
                  </nav>
                )}

                <section className="ta-panel m-plate">
                  <div className="ta-panel-head">
                    <h3 className="t-eyebrow">WHAT PRAGYA PROMISED</h3>
                    <span className="ta-col-note t-mono">{chosen.status}</span>
                  </div>
                  {/* Her committed sentence, verbatim. The only part of the
                      conversation that is attributably about this brief. */}
                  <blockquote className="ta-card-words">{chosen.promise}</blockquote>
                  <dl className="ta-clauses">
                    <div className="ta-clause">
                      <dt className="t-eyebrow">OPENED</dt>
                      <dd className="ta-clause-val">{when(chosen.opened_at)}</dd>
                    </div>
                    <div className="ta-clause">
                      <dt className="t-eyebrow">BRIEF</dt>
                      <dd className="ta-clause-val t-mono">
                        {chosen.brief_id.slice(0, 8)}
                      </dd>
                    </div>
                  </dl>
                </section>

                <section className="ta-panel m-plate">
                  <h3 className="t-eyebrow">THE BOARD RUN</h3>
                  {chosen.board_run !== null ? (
                    <dl className="ta-clauses">
                      <div className="ta-clause">
                        <dt className="t-eyebrow">RUN</dt>
                        <dd className="ta-clause-val t-mono">
                          {chosen.board_run.run_id.slice(0, 8)}
                        </dd>
                      </div>
                      <div className="ta-clause">
                        <dt className="t-eyebrow">STATUS</dt>
                        <dd className="ta-clause-val">{chosen.board_run.status}</dd>
                      </div>
                      {/* A run that has not started, or has not finished, prints
                          no time at all. Never "—", never a zero duration. */}
                      {chosen.board_run.started_at !== null && (
                        <div className="ta-clause">
                          <dt className="t-eyebrow">STARTED</dt>
                          <dd className="ta-clause-val">
                            {when(chosen.board_run.started_at)}
                          </dd>
                        </div>
                      )}
                      {chosen.board_run.completed_at !== null && (
                        <div className="ta-clause">
                          <dt className="t-eyebrow">FINISHED</dt>
                          <dd className="ta-clause-val">
                            {when(chosen.board_run.completed_at)}
                          </dd>
                        </div>
                      )}
                    </dl>
                  ) : (
                    <p className="ta-note">
                      This brief dispatched no run, so there is nothing to follow
                      through to. That is a fact about the brief and not a missing
                      field.
                    </p>
                  )}
                </section>

                {/* --------------------------------------------- the four absences
                    Each was a block on this column: the conversation, the terms,
                    what the role may touch, and where it would sit. */}
                <Absence
                  view={briefs}
                  field="turns"
                  label="THE BRIEF AS A CONVERSATION"
                  lead="The back-and-forth that produced this brief cannot be shown."
                />
                <Absence
                  view={briefs}
                  field="clauses"
                  label="THE BRIEF AS IT STANDS"
                  lead="What the role is for, its ceiling and who it reports to are not kept."
                />
                <Absence
                  view={briefs}
                  field="may_touch"
                  label="WHAT IT MAY TOUCH"
                  lead="Nothing records what this role would be granted or kept back from."
                />
                <Absence
                  view={briefs}
                  field="district"
                  label="WHERE IT WOULD SIT"
                  lead="No district and no quarter are attached to a brief."
                />
              </>
            )}
          </div>
        </div>

        {/* =========================================================== the exam */}
        <div className="ta-col">
          <div className="ta-col-head">
            <h2 className="t-eyebrow">THE EXAM · WORK YOU HAVE ALREADY HANDLED</h2>
            <span className="ta-col-note t-mono">
              {cases === null ? "" : `as of ${when(cases.as_of)}`}
            </span>
          </div>

          <div className="ta-col-scroll">
            {casesFailure !== null ? (
              <Failed
                alone={false}
                what="the past cases"
                reason={casesFailure.reason}
                onRetry={casesFailure.retry}
              />
            ) : cases === null ? null : (
              <Exam cases={cases} />
            )}
          </div>
        </div>

        {/* ============================================== shortlist gap · leaving */}
        <div className="ta-col">
          <div className="ta-col-head">
            <h2 className="t-eyebrow">SHORTLIST &amp; INTERVIEW</h2>
            <span className="ta-col-note t-mono">not read back</span>
          </div>

          <div className="ta-col-scroll">
            {/* §7.4: where the platform has a real gap, render the gap. This one
                is the surface's own statement, not an endpoint's, and it is
                written as such — the read models name what *they* cannot answer,
                and "which candidates the board proposed" is a read nobody built
                rather than a field one of them declined. */}
            <section className="ta-panel m-plate" data-sunken>
              <div className="ta-panel-head">
                <h3 className="t-eyebrow">NO SHORTLIST IS READ BACK</h3>
                <span className="ta-gap-state">
                  <span className="m-lamp" aria-hidden="true" />
                  no source
                </span>
              </div>
              <p className="ta-note">
                A brief is put to the Meta-Agent board and the run that carries it
                is recorded — you can see it on the left. The brief read
                deliberately does <strong>not</strong> project that run's output:
                composing candidates out of a result blob is exactly the invention
                the endpoint exists to refuse. So this column has no cards to
                draw, and drawing four would be the one thing this room must never
                do.
              </p>
              <p className="ta-note">
                The interview is the same absence one level down. It would be a
                scoped twin session putting a candidate in front of the cases in
                the middle column; <strong>no such session is run anywhere</strong>
                , and nothing joins a candidate to a case, so there are no
                attempts, no verdicts and no traces to compare against what
                actually happened.
              </p>
              <p className="ta-note">
                What survives from the hire block that stood here: every hire lands
                at <strong>A1</strong> whatever an interview shows. An interview is
                evidence about the past and autonomy is a claim about the future,
                and the only thing that moves it is thirty days of acts you watched
                land in your own tray.
              </p>
            </section>

            <Leaving onEcho={onEcho} />
          </div>
        </div>
      </div>
    </section>
  );
}

/** Which of the five a brief can be evidenced at. Never more than two. */
function stateOf(key: string, brief: Brief | undefined): "done" | "here" | "ahead" {
  if (brief === undefined) return key === "brief" ? "here" : "ahead";
  if (key === "brief") return "done";
  if (key === "shortlist") return brief.board_run !== null ? "here" : "ahead";
  return "ahead";
}

/* ========================================================================== */
/*  AN ABSENCE                                                                */
/* ========================================================================== */

/**
 * A field the endpoint says it cannot answer, drawn where the field would have
 * been. The lead is this surface's — one sentence in the room's voice — and the
 * reason is the endpoint's, printed verbatim in `t-mono` at caption size. Both,
 * always: the reason alone is a paragraph of backend prose in the middle of a
 * hiring room, and the lead alone throws away the only checkable thing on the
 * block. Nothing renders at all if the server did not name this field, because a
 * client-side fallback would silently replace nine specific reasons with one
 * vague one.
 */
function Absence({
  view,
  field,
  label,
  lead,
}: {
  view: { absent: { field: string; why: string }[] };
  field: string;
  label: string;
  lead: string;
}) {
  const why = absentIn(view, field);
  if (why === null) return null;
  return (
    <div className="m-well ta-absence">
      <span className="t-eyebrow">{label}</span>
      <p className="ta-absence-lead">
        {/* Unlit lamp. An absence is not a fault state — a terracotta dot here
            would teach an owner that their platform is broken rather than
            young, which is the reading `Empty` is careful to avoid too. */}
        <span className="m-lamp" aria-hidden="true" />
        {lead}
      </p>
      <p className="ta-absence-why t-mono">{why}</p>
    </div>
  );
}

/* ========================================================================== */
/*  THE EXAM                                                                  */
/* ========================================================================== */

function Exam({ cases }: { cases: PastCasesView }) {
  const replayable = cases.cases.filter((c) => c.replayable === true).length;
  const blocked = cases.cases.filter((c) => c.replayable === false).length;
  const unknown = cases.cases.filter((c) => c.replayable === null).length;

  return (
    <>
      <section className="ta-panel m-plate">
        <h3 className="ta-iv-title t-display">
          {cases.cases.length} case{cases.cases.length === 1 ? "" : "s"} your estate
          has already handled
        </h3>
        <p className="ta-iv-lead">
          A candidate is not read off a CV but watched handling work whose ending
          is already known. Each case below is a real event that arrived, the
          records it turned on, and what actually happened next.
        </p>
        {cases.cases.length > 0 && (
          <div className="ta-iv-chips">
            {/* Counts, never authored. A zero count is omitted rather than
                printed: "0 blocked" and "no case was blocked" read the same to a
                machine and differently to a person. */}
            {replayable > 0 && <span className="m-chip">{replayable} replayable</span>}
            {blocked > 0 && <span className="m-chip">{blocked} cannot be replayed</span>}
            {unknown > 0 && <span className="m-chip">{unknown} cannot be determined</span>}
          </div>
        )}
        {/* The flag's promise in the read model's own words — rendered wherever
            the flag is, because a claim that lives only in a design document is
            a claim the surface will eventually overstate. */}
        <p className="ta-note">{cases.replayable_means}</p>
        <p className="ta-note">
          The window is <strong>{cases.max_window_days} days</strong>, which is the
          longest a scenario scope may ask for.
        </p>
      </section>

      {cases.cases.length === 0 ? (
        <Empty
          icon="record"
          title="No work has been picked up and finished yet."
          body="The exam is built from signals that actually arrived and were consumed by a run. Until something has come in and been handled, there is nothing a candidate could be put in front of — and an exam composed of made-up cases would measure nothing."
          note="consumed signals · none on record"
        />
      ) : (
        cases.cases.map((c) => <Case key={c.case_id} kase={c} />)
      )}

      {/* --------------------------------------------------- the five absences */}
      <Absence
        view={cases}
        field="what"
        label="WHAT WAS IN FRONT OF WHOEVER HELD IT"
        lead="No case carries a written account of the situation."
      />
      <Absence
        view={cases}
        field="actually"
        label="WHAT ACTUALLY HAPPENED, IN PROSE"
        lead="The structured answer is above each case; the sentence that narrates it is not written anywhere."
      />
      <Absence
        view={cases}
        field="party"
        label="THE COUNTERPARTY"
        lead="No case names who it was with."
      />
      <Absence
        view={cases}
        field="answers"
        label="THE CANDIDATE'S ATTEMPT"
        lead="Nothing has answered any of these cases, so there is no attempt to set beside what happened."
      />
      <Absence
        view={cases}
        field="brief_relevance"
        label="WHICH CASES BELONG TO THIS BRIEF"
        lead="These are your estate's recent handled work, not a set selected for the role on the left."
      />
    </>
  );
}

function Case({ kase }: { kase: PastCase }) {
  const [open, setOpen] = useState(false);

  return (
    <article className="ta-case m-plate">
      <header className="ta-case-head">
        <span className="ta-case-ref">
          <span className="t-eyebrow">
            {kase.signal_type} · {when(kase.when)}
          </span>
          <h3 className="ta-case-party t-display">{kase.source}</h3>
        </span>
        <span className="ta-case-tags">
          {kase.urgency !== null && <span className="m-chip">{kase.urgency}</span>}
          {kase.trust !== null && <span className="m-chip">{kase.trust}</span>}
        </span>
      </header>

      <div className="m-well ta-compare">
        <div className="ta-compare-half" data-side="real">
          <span className="t-eyebrow">WHAT IT TURNED ON</span>
          {kase.records.length > 0 ? (
            <ul className="ta-recs">
              {kase.records.map((r) => (
                <li className="ta-rec" key={r.record_id}>
                  <span className="ta-rec-label t-mono">{r.label}</span>
                  {/* A deleted record is a lamp and a word — the record is still
                      the one the case turned on, and saying so is the point. */}
                  {r.deleted && (
                    <span className="ta-rec-gone">
                      <span className="m-lamp" data-negative aria-hidden="true" />
                      deleted since
                    </span>
                  )}
                  {r.updated_at !== null && (
                    <span className="ta-rec-when t-mono">
                      last touched {when(r.updated_at)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="ta-compare-text t-mono">
              This case named no record in your own records.
            </p>
          )}

          {kase.unresolved_refs.length > 0 && (
            <p className="ta-compare-text t-mono">
              {kase.unresolved_refs.length} ref
              {kase.unresolved_refs.length === 1 ? "" : "s"} looked like a record
              and matched nothing.
            </p>
          )}
          {kase.other_refs.length > 0 && (
            <p className="ta-compare-text t-mono">
              also names {kase.other_refs.map((r) => r.ref).join(", ")}
            </p>
          )}
        </div>

        <hr className="m-rule-fade" />

        <div className="ta-compare-half" data-side="candidate">
          <span className="t-eyebrow">WHAT HAPPENED</span>
          {kase.outcome !== null ? (
            <>
              <p className="ta-compare-text">
                {kase.outcome.handled_by !== null
                  ? `${kase.outcome.handled_by.name} picked it up`
                  : "A run picked it up"}
                {" · "}
                {kase.outcome.status}
                {kase.outcome.completed_at !== null &&
                  ` · finished ${when(kase.outcome.completed_at)}`}
              </p>
              {kase.outcome.approvals.length > 0 && (
                <ul className="ta-appr">
                  {kase.outcome.approvals.map((a) => (
                    <li className="ta-appr-row" key={a.approval_id}>
                      <span className="t-mono">
                        {a.checkpoint_key ?? a.checkpoint_trigger ?? a.approval_id.slice(0, 8)}
                      </span>
                      <span className="m-chip">{a.status}</span>
                      {a.responded_at !== null && (
                        <span className="ta-rec-when t-mono">
                          answered {when(a.responded_at)}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="ta-compare-text t-mono">
              The run that consumed this signal is no longer on record.
            </p>
          )}
        </div>
      </div>

      {/* Three states, and the third is the point: a check that cannot see
          something must not report it as a refusal. `unknown` is not `blocked`,
          exactly as `untested` is not `unknown` in the grade vocabulary. */}
      {kase.replayable === true ? (
        <div className="ta-verdict">
          <span className="ta-verdict-word">
            <span className="m-lamp" data-positive aria-hidden="true" />
            can be replayed
          </span>
          <p className="ta-verdict-note">
            The event is inside the longest window a scope may ask for, and every
            record it turned on was touched inside that window too.
          </p>
        </div>
      ) : kase.replayable === false ? (
        <div className="ta-verdict">
          <span className="ta-verdict-word">
            <span className="m-lamp" data-negative aria-hidden="true" />
            cannot be replayed
          </span>
          <p className="ta-verdict-note">{kase.blocked_because}</p>
        </div>
      ) : (
        <div className="m-well ta-untested" data-deep>
          <span className="t-eyebrow">CANNOT BE DETERMINED · NOT A REFUSAL</span>
          <p className="ta-verdict-note">{kase.unknown_because}</p>
        </div>
      )}

      <button
        className="ta-trace-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="chevron" size={12} className="ta-trace-caret" />
        {open ? "hide the ids" : "the ids"}
      </button>
      {open && (
        <div className="m-well ta-trace vh-enter-fade" data-deep>
          <ol>
            <li>
              <span className="ta-trace-at">signal</span>
              <span className="ta-trace-what">{kase.case_id}</span>
            </li>
            {kase.outcome !== null && (
              <li>
                <span className="ta-trace-at">run</span>
                <span className="ta-trace-what">{kase.outcome.run_id}</span>
              </li>
            )}
            {kase.records.map((r) => (
              <li key={r.record_id}>
                <span className="ta-trace-at">{r.def}</span>
                <span className="ta-trace-what">{r.record_id}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </article>
  );
}

/* ========================================================================== */
/*  WHEN SOMEONE LEAVES — VG-18, no longer blocked                            */
/* ========================================================================== */

/**
 * The four designed steps, now the four steps that run. Kept as a list because
 * the point of the block was always that termination is a *workflow* and not a
 * delete, and a bare button would lose that — but every sentence is now written
 * in the present tense, because every one of them happens.
 */
const TERMINATION_STEPS: { label: string; what: string }[] = [
  {
    label: "In-flight work stops it",
    what: "A termination refuses outright while runs are still live, and names them. A refusal, not a queue: a termination that silently strands a half-finished chase is the worst version of this.",
  },
  {
    label: "The exit interview",
    what: "Tenure, the runs, how many completed and how many failed — composed from what already exists. Deterministic, and no written-up prose.",
  },
  {
    label: "The handover memo",
    what: "Filed to the Library as an Artifact. What was in flight and which approvals remain yours — pending approvals survive the colleague, because they belong to you.",
  },
  {
    label: "The Gallery keeps the record",
    what: "The termination stamp goes on the entity before the soft-delete, so colleagues past is a query and not a new table. Usage rows, echoes and influence records all survive.",
  },
];

function Leaving({ onEcho }: { onEcho: (msg: string) => void }) {
  const colleagues = useResource(fetchEntities);
  const [asked, setAsked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<TerminationRefusal | null>(null);
  const [done, setDone] = useState<TerminationDone | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  /** Ids terminated in this session — the roster read is captured once, so a
   *  row that has left has to be remembered rather than re-fetched. */
  const [gone, setGone] = useState<string[]>([]);

  const roster =
    colleagues.phase === "ready"
      ? colleagues.value.filter(
          (e) =>
            e.type === "AGENT" &&
            e["is_template"] !== true &&
            e["status"] !== "DELETED" &&
            !isGateway(e) &&
            !gone.includes(e.id),
        )
      : [];

  async function terminate(entity: EntityOut): Promise<void> {
    setBusy(true);
    setRefusal(null);
    setFailure(null);
    try {
      const outcome = await terminateColleague(entity.id);
      setDone(outcome);
      setGone((ids) => [...ids, entity.id]);
      setAsked(null);
      onEcho(`ended ${nameOf(entity)}’s engagement`);
    } catch (raised) {
      const refused = parseTerminationRefusal(raised);
      if (refused !== null) {
        setRefusal(refused);
      } else {
        setFailure(
          raised instanceof Error && raised.message !== ""
            ? raised.message
            : "The estate did not answer.",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ta-panel m-plate">
      <div className="ta-panel-head">
        <h3 className="t-eyebrow">WHEN SOMEONE LEAVES</h3>
        <span className="ta-gap-state">
          <span className="m-lamp" data-positive aria-hidden="true" />
          wired · all four steps
        </span>
      </div>

      <ol className="ta-steps">
        {TERMINATION_STEPS.map((d) => (
          <li className="ta-step" key={d.label}>
            <span className="ta-step-text">
              <span className="ta-step-label">{d.label}</span>
              <span className="ta-step-what">{d.what}</span>
            </span>
          </li>
        ))}
      </ol>

      <p className="ta-note">
        Ending an engagement is a <strong>plain governed act</strong>, and that is
        a decision rather than an omission: stopping a colleague must never be
        harder than hiring one, so there is no step-up on this path and no passkey
        is asked for. Nothing here deletes the audit.
      </p>

      {/* ------------------------------------------------------------ the act */}
      {colleagues.phase === "pending" ? (
        <Scaffold label="Your colleagues">
          <div className="ta-leaving-scaffold">
            <Bar width="sm" />
            <Bar width="md" />
          </div>
        </Scaffold>
      ) : colleagues.phase === "failed" ? (
        <Failed
          alone={false}
          what="your colleagues"
          reason={colleagues.reason}
          onRetry={colleagues.retry}
        />
      ) : roster.length === 0 ? (
        <p className="ta-note">
          There is nobody working for you, so there is nobody to end an engagement
          with.
        </p>
      ) : (
        <ul className="ta-leaving">
          {roster.map((e) => (
            <li className="ta-leaving-row" key={e.id}>
              <span className="m-portrait-well ta-leaving-face">
                <Portrait id={artKeyFor(e.name)} size={32} />
              </span>
              <span className="ta-leaving-text">
                <span className="ta-leaving-name">{nameOf(e)}</span>
                <span className="t-mono ta-leaving-id">{e.id.slice(0, 8)}</span>
              </span>
              {asked === e.id ? (
                <span className="ta-leaving-confirm">
                  <button
                    className="m-btn"
                    disabled={busy}
                    onClick={() => void terminate(e)}
                  >
                    <Icon name="check" size={13} />
                    End it
                  </button>
                  <button
                    className="m-btn"
                    data-rank="quiet"
                    disabled={busy}
                    onClick={() => setAsked(null)}
                  >
                    Keep
                  </button>
                </span>
              ) : (
                <button
                  className="m-btn"
                  data-rank="quiet"
                  onClick={() => {
                    setAsked(e.id);
                    setRefusal(null);
                    setFailure(null);
                  }}
                >
                  End the engagement
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* A 409 is the server's designed answer and not an error. It names the
          runs, so they are printed rather than counted. */}
      {refusal !== null && (
        <div className="m-well ta-missing" data-deep role="status">
          <span className="t-eyebrow">REFUSED · WORK IS STILL LIVE</span>
          <p className="ta-verdict-note">{refusal.reason}</p>
          <ul>
            {refusal.running_run_ids.map((id) => (
              <li className="t-mono" key={id}>
                {id}
              </li>
            ))}
          </ul>
        </div>
      )}

      {failure !== null && (
        <div className="m-well ta-missing" data-deep role="status">
          <span className="t-eyebrow">NOT ENDED</span>
          <p className="ta-verdict-note">
            Nothing was changed. The estate answered: {failure}
          </p>
        </div>
      )}

      {done !== null && (
        <div className="m-well ta-missing" data-deep role="status">
          <span className="t-eyebrow">ENDED · {done.summary.name.toUpperCase()}</span>
          <p className="ta-verdict-note">
            {done.summary.runs_completed} of {done.summary.runs_total} runs
            completed.
            {done.summary.pending_approvals > 0 &&
              ` ${done.summary.pending_approvals} approval${done.summary.pending_approvals === 1 ? "" : "s"} stay with you — they were always yours.`}
          </p>
          {/* The memo id is printed only where the artifact was actually filed.
              An absent id is not "no memo": it is the memo store declining, and
              inventing a link to it would be worse than saying nothing. */}
          {done.memo_artifact_id !== null && (
            <p className="ta-note t-mono">
              handover memo · {done.memo_artifact_id}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

/* ========================================================================== */
/*  PENDING                                                                   */
/* ========================================================================== */

/**
 * The pending state (D7 §3.1) — this room's own structure with the words not
 * yet in it. No spinner: this is one of the seventeen.
 *
 * Plates first, bars inside them. `vh-skeleton`'s ground is a ~6/255 delta on
 * the raw canvas, so a bar on the page background draws nothing at all.
 */
function TalentScaffold() {
  return (
    <section className="ta">
      <Scaffold label="The Talent Office">
        <div className="ta-head">
          <div className="ta-head-top">
            <div className="ta-scaffold-title">
              <Bar width="xs" />
              <Bar width="md" tall />
              <Lines n={2} />
            </div>
          </div>
          <ol className="ta-stages">
            {Array.from({ length: 5 }, (_, i) => (
              <li className="ta-stage" key={i}>
                <Bar width="sm" />
                <Lines n={2} />
              </li>
            ))}
          </ol>
        </div>
        <div className="ta-cols">
          {Array.from({ length: 3 }, (_, col) => (
            <div className="ta-col" key={col}>
              <div className="ta-col-head">
                <Bar width="sm" />
              </div>
              <div className="ta-col-scroll">
                {Array.from({ length: 2 }, (_, i) => (
                  <div className="ta-panel m-plate" key={i}>
                    <Bar width="xs" />
                    <Lines n={4} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Scaffold>
    </section>
  );
}
