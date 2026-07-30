import { useState } from "react";
import { Icon } from "../components/Icon";
import { Portrait } from "../components/Portrait";
import {
  AUTONOMY_MEANS,
  BRIEF,
  CANDIDATES,
  GRADE_MEANS,
  HIRE,
  INCUMBENT,
  PAST_CASES,
  STAGES,
  TERMINATION,
  VERDICT_MEANS,
  type BriefTurn,
  type Candidate,
} from "../fixtures/talent";
import "./talent.css";

/**
 * The Talent Office · depth 2 · S (D6 §9).
 *
 * Answers **RD-7** directly: hiring a colleague was built as an "L9 sheet
 * equivalent" and inherited a fallback's budget, when it is in fact the most
 * consequential thing a tenant does in this product — every other surface is
 * about work that a colleague hired here will go on to do.
 *
 * Four decisions a reader could not reverse-engineer from the markup:
 *
 *  1. **The interview holds the known answer beside the attempt, in one well.**
 *     A CV is a claim; a replay against a case whose ending you already know is
 *     a measurement. So each case prints what *actually happened* first and the
 *     candidate's attempt second, inside a single `m-well` split by a hairline
 *     — two separate wells would read as two unrelated facts rather than as a
 *     comparison. The verdict then compares them in one sentence, and the trace
 *     is one flip away for anyone who wants to check the sentence.
 *  2. **`stopped-and-asked` is rendered as a plain state, not a failure.** At A1
 *     every act waits for the owner anyway, so stopping is frequently correct —
 *     and the thing that is *not* correct is stopping on everything, which reads
 *     off the count rather than off the colour. Terracotta is reserved for the
 *     one candidate whose replay would have cost real money, and for the tool
 *     ask that sits outside the brief.
 *  3. **The gold budget is spent entirely on the hire.** The stage rail's "you
 *     are here", the recommended candidate and the selected candidate all get
 *     surface, edge, ticks and a *word* — never gold. A recommendation is
 *     neither "this needs you" nor "this is certified", and a rail that glowed
 *     would out-shout the one certified act on the surface.
 *  4. **The hire block is pinned to the foot of the interview column.** It is
 *     the act the room exists for, and the A1 rule is stated there in prose:
 *     autonomy rises on thirty days of watched acts, never on an interview. That
 *     is also why no control on this surface can raise a band — the absence is
 *     explained rather than left to look like an oversight.
 *
 * Density: this is the **operator** view — four candidates side by side with the
 * recommendation carried by ticks, an eyebrow and its evidence. The novice
 * variant would render the recommended candidate alone with the other three
 * behind "see others"; the recommendation copy is written to stand on its own so
 * that variant is a disclosure, not a rewrite.
 */
export function TalentSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const [turns, setTurns] = useState<BriefTurn[]>(BRIEF.turns);
  const [draft, setDraft] = useState("");
  const [activeId, setActiveId] = useState<string>(
    CANDIDATES.find((c) => c.recommended)?.id ?? CANDIDATES[0]!.id,
  );
  const [openTrace, setOpenTrace] = useState<string | null>(null);
  const [hiredId, setHiredId] = useState<string | null>(null);

  const active: Candidate = CANDIDATES.find((c) => c.id === activeId) ?? CANDIDATES[0]!;
  const hired = hiredId ? (CANDIDATES.find((c) => c.id === hiredId) ?? null) : null;

  /* Counts are computed, never authored — the summary sentence beside them is
     the engine's own words, and the two must not be able to disagree. */
  const answers = active.interview.answers;
  const replayed = answers.filter((a) => a.grade === "replay").length;
  const notRun = answers.filter((a) => a.grade === "untested").length;

  return (
    <section className="ta">
      {/* ================================================================ head */}
      <header className="ta-head">
        <div className="ta-head-top">
          <div>
            <span className="t-eyebrow">THE TALENT OFFICE · {BRIEF.district.toUpperCase()}</span>
            <h1 className="ta-title t-display">Hiring a {BRIEF.role.toLowerCase()} colleague</h1>
            <p className="ta-lead">
              A colleague is hired the way a person is — a brief, a shortlist, an
              interview, thirty days, and then a decision. The interview runs each
              candidate against work you have already done, so what you compare is
              their call against yours.
            </p>
          </div>
          <div className="ta-head-meta">
            <span className="m-chip">
              <Icon name="colleague" size={12} />
              {CANDIDATES.length} candidates
            </span>
            <span className="m-chip">brief opened {BRIEF.opened}</span>
            <span className="m-chip">{BRIEF.quarter}</span>
          </div>
        </div>

        {/* The five stages, each with what it means. No gold: see docstring §3. */}
        <ol className="ta-stages">
          {STAGES.map((s) => (
            <li className="ta-stage" key={s.key} data-state={s.state}>
              <span className="ta-stage-top">
                <span className="ta-stage-mark" aria-hidden="true" />
                <span className="ta-stage-label">{s.label}</span>
                {s.state === "here" && (
                  <span className="ta-stage-here t-mono">you are here</span>
                )}
              </span>
              <span className="ta-stage-means">{s.means}</span>
            </li>
          ))}
        </ol>
      </header>

      <div className="ta-cols">
        {/* ========================================================= the brief */}
        <div className="ta-col">
          <div className="ta-col-head">
            <h2 className="t-eyebrow">THE BRIEF</h2>
            <span className="ta-col-note t-mono">as a conversation, because it was one</span>
          </div>

          <div className="ta-col-scroll">
            <section className="ta-panel m-plate">
              <div className="ta-turns">
                {turns.map((t, i) => (
                  <div className="ta-turn" key={`${t.who}-${i}`} data-who={t.who}>
                    <span className="t-eyebrow">{t.who === "you" ? "YOU" : "PRAGYA"}</span>
                    <p className="ta-turn-said">{t.said}</p>
                  </div>
                ))}
              </div>

              {/* A brief you cannot add a line to is a brief somebody else wrote. */}
              <form
                className="ta-brief-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  const said = draft.trim();
                  if (!said) return;
                  setTurns((list) => [...list, { who: "you", said }]);
                  setDraft("");
                  onEcho(`added “${said}” to the brief`);
                }}
              >
                <input
                  className="ta-brief-input"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Add a line to the brief"
                  aria-label="Add a line to the brief"
                />
                <button className="m-btn" type="submit" disabled={draft.trim() === ""}>
                  <Icon name="forward" size={13} />
                  Add
                </button>
              </form>
            </section>

            <section className="ta-panel m-plate">
              <h3 className="t-eyebrow">THE BRIEF AS IT STANDS</h3>
              <dl className="ta-clauses">
                {BRIEF.clauses.map((c) => (
                  <div className="ta-clause" key={c.label}>
                    <dt className="t-eyebrow">{c.label.toUpperCase()}</dt>
                    <dd className="ta-clause-val">{c.value}</dd>
                  </div>
                ))}
              </dl>
            </section>

            <section className="ta-panel m-plate">
              <div className="ta-panel-head">
                <h3 className="t-eyebrow">WHAT IT MAY TOUCH</h3>
                <span className="ta-col-note t-mono">
                  {BRIEF.mayTouch.filter((p) => p.withheld).length} kept back
                </span>
              </div>
              <ul className="ta-touch">
                {BRIEF.mayTouch.map((p) => (
                  <li className="ta-touch-item" key={p.name} data-withheld={p.withheld || undefined}>
                    <span className="m-lamp ta-touch-lamp" aria-hidden="true" />
                    <span className="ta-touch-text">
                      <span className="ta-touch-name">
                        {p.name}
                        <span className="m-chip ta-touch-word">{p.kind}</span>
                        {p.withheld && <span className="m-chip ta-touch-word">withheld</span>}
                      </span>
                      <span className="ta-touch-note">{p.note}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </section>

            {/* ------------------------------------------------- VG-18, blocked
                Drawn as designed, and stated as blocked. No control appears,
                because there is nothing behind one. */}
            <section className="ta-panel m-plate" data-sunken>
              <div className="ta-panel-head">
                <h3 className="t-eyebrow">WHEN SOMEONE LEAVES</h3>
                <span className="ta-gap-state">
                  <span className="m-lamp" aria-hidden="true" />
                  blocked · {TERMINATION.gap}
                </span>
              </div>

              <p className="ta-note">
                Designed, and not wired. What the platform has today:{" "}
                <strong>{TERMINATION.have}</strong>
              </p>

              <ol className="ta-steps">
                {TERMINATION.designed.map((d) => (
                  <li className="ta-step" key={d.label}>
                    <span className="ta-step-text">
                      <span className="ta-step-label">{d.label}</span>
                      <span className="ta-step-what">{d.what}</span>
                    </span>
                  </li>
                ))}
              </ol>

              <div className="m-well ta-missing" data-deep>
                <span className="t-eyebrow">WHAT IS MISSING</span>
                <ul>
                  {TERMINATION.missing.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              </div>

              <p className="ta-note">{TERMINATION.note}</p>
            </section>
          </div>
        </div>

        {/* ===================================================== the shortlist */}
        <div className="ta-col">
          <div className="ta-col-head">
            <h2 className="t-eyebrow">SHORTLIST · {CANDIDATES.length} FROM THE META-AGENT BOARD</h2>
            <span className="ta-col-note t-mono">
              compared side by side · one is recommended, with its reason
            </span>
          </div>

          <div className="ta-col-scroll">
            <div className="ta-cards vh-stagger">
              {CANDIDATES.map((c, i) => {
                const isActive = c.id === active.id;
                const outside = c.tools.filter((t) => t.outsideBrief);
                return (
                  <article
                    key={c.id}
                    className={c.recommended ? "ta-card m-plate m-ticks" : "ta-card m-plate"}
                    data-active={isActive || undefined}
                    style={{ ["--i" as string]: i }}
                  >
                    <div className="ta-card-flag">
                      {c.recommended && <span className="t-eyebrow">RECOMMENDED</span>}
                      {isActive && <span className="t-eyebrow">IN THE INTERVIEW</span>}
                      {hired?.id === c.id && <span className="t-eyebrow">HIRED AT A1</span>}
                    </div>

                    <div className="ta-card-top">
                      <span className="m-portrait-well ta-card-face">
                        <Portrait
                          id={c.id}
                          size={44}
                          title={`${c.name} — a generated portrait of a candidate, not a photograph`}
                        />
                      </span>
                      <span className="ta-card-ident">
                        <h3 className="ta-card-name t-display">{c.name}</h3>
                        <span className="ta-card-role t-mono">board role · {c.boardRole}</span>
                        <span className="ta-card-origin t-mono">{c.origin}</span>
                      </span>
                    </div>

                    <blockquote className="ta-card-words">{c.ownWords}</blockquote>

                    {c.recommended && c.recommendedBecause && (
                      <div className="m-well ta-why">
                        <span className="t-eyebrow">WHY THIS ONE</span>
                        <p className="ta-why-text">{c.recommendedBecause}</p>
                      </div>
                    )}

                    <dl className="ta-charter">
                      {c.charter.map((cl) => (
                        <div className="ta-charter-row" key={cl.label}>
                          <dt className="t-eyebrow">{cl.label.toUpperCase()}</dt>
                          <dd className="ta-charter-val">{cl.value}</dd>
                        </div>
                      ))}
                    </dl>

                    <div className="ta-field">
                      <span className="t-eyebrow">PROPOSED TOOLS</span>
                      <div className="ta-tools">
                        {c.tools.map((t) => (
                          <span
                            className="m-chip ta-tool"
                            key={t.name}
                            data-outside={t.outsideBrief || undefined}
                            title={t.note}
                          >
                            {t.name}
                            {t.outsideBrief && " · outside the brief"}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* A candidate asking for something the brief withholds is a
                        conflict, not a fault — so it is a lamp and a word, and it
                        names the choice it forces rather than scoring the person. */}
                    {outside.length > 0 && (
                      <div className="ta-verdict">
                        <span className="ta-verdict-word">
                          <span className="m-lamp" data-negative aria-hidden="true" />
                          asks for what the brief keeps back
                        </span>
                        <p className="ta-verdict-note">
                          {outside.map((t) => t.name).join(", ")} — {outside[0]!.note}. Hiring{" "}
                          {c.name} means either granting it or hiring a narrower version of
                          the role.
                        </p>
                      </div>
                    )}

                    {/* Cost per month. A null figure renders as its reason, never
                        as ₹0 and never as a dash (§7.1). */}
                    {c.costPerMonthINR !== null ? (
                      <div className="ta-field">
                        <span className="t-eyebrow">COST</span>
                        <div className="ta-cost">
                          <span className="t-figure ta-cost-fig">
                            ₹{c.costPerMonthINR.toLocaleString("en-IN")}
                          </span>
                          <span className="ta-cost-per">per month</span>
                        </div>
                        {c.costBasis && <p className="ta-cost-basis">{c.costBasis}</p>}
                      </div>
                    ) : (
                      <div className="m-well ta-cost-absent" data-deep>
                        <span className="t-eyebrow">COST · NO FIGURE</span>
                        <p className="ta-why-text">{c.costAbsence}</p>
                      </div>
                    )}

                    <div className="ta-card-acts">
                      {isActive ? (
                        <button
                          className="m-btn"
                          data-rank="quiet"
                          onClick={() => onEcho(`opened ${c.name}’s proposed charter`)}
                        >
                          <Icon name="record" size={13} />
                          The full charter
                        </button>
                      ) : (
                        <button
                          className="m-btn"
                          onClick={() => {
                            setActiveId(c.id);
                            setOpenTrace(null);
                            onEcho(`interviewed ${c.name} against your March cases`);
                          }}
                        >
                          <Icon name="search" size={13} />
                          Interview against past cases
                        </button>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        </div>

        {/* ===================================================== the interview */}
        <div className="ta-col">
          <div className="ta-col-head">
            <h2 className="t-eyebrow">THE INTERVIEW · A SCOPED TWIN SESSION</h2>
            <span className="ta-col-note t-mono">{active.interview.runId}</span>
          </div>

          <div className="ta-col-scroll">
            <section className="ta-panel m-plate">
              <h3 className="ta-iv-title t-display">
                {active.name}, against {PAST_CASES.length} cases you already know
              </h3>
              <p className="ta-iv-lead">
                Every case below has already happened in your estate, and you know
                how each one ended. The candidate was put in front of it in the twin
                with only what was knowable at the time — nothing from after.
              </p>
              <div className="ta-iv-chips">
                <span className="m-chip">{replayed} replayed</span>
                {notRun > 0 && <span className="m-chip">{notRun} could not be run</span>}
                <span className="m-chip">
                  this sitting cost ₹{active.interview.costINR.toFixed(2)}
                </span>
              </div>
              <p className="ta-iv-summary">{active.interview.summary}</p>
              <p className="ta-note">{active.interview.scope}</p>
            </section>

            {PAST_CASES.map((c) => {
              const a = answers.find((x) => x.ref === c.ref);
              if (!a) return null;
              const v = a.verdict ? VERDICT_MEANS[a.verdict] : null;
              const traceOpen = openTrace === `${active.id}:${c.ref}`;

              return (
                <article className="ta-case m-plate" key={c.ref}>
                  <header className="ta-case-head">
                    <span className="ta-case-ref">
                      <span className="t-eyebrow">
                        {c.ref} · {c.when}
                      </span>
                      <h3 className="ta-case-party">{c.party}</h3>
                    </span>
                    <span className="m-chip" title={GRADE_MEANS[a.grade]}>
                      {a.grade}
                    </span>
                  </header>

                  <p className="ta-case-what">{c.what}</p>

                  <div className="m-well ta-compare">
                    <div className="ta-compare-half" data-side="real">
                      <span className="t-eyebrow">WHAT ACTUALLY HAPPENED</span>
                      <p className="ta-compare-text">{c.actually}</p>
                    </div>

                    <hr className="m-rule-fade" />

                    <div className="ta-compare-half" data-side="candidate">
                      <span className="t-eyebrow">WHAT {active.name.toUpperCase()} DID</span>
                      {a.did !== null ? (
                        <>
                          <p className="ta-compare-text">{a.did}</p>
                          {a.words !== null && (
                            <blockquote className="ta-compare-words">{a.words}</blockquote>
                          )}
                        </>
                      ) : (
                        /* Nothing ran, so nothing is shown. `untested` is not
                           `unknown`: the words say never tried, not ungradeable. */
                        <p className="ta-compare-text t-mono">{GRADE_MEANS.untested}</p>
                      )}
                    </div>
                  </div>

                  {v && a.verdictNote ? (
                    <div className="ta-verdict">
                      <span className="ta-verdict-word">
                        <span
                          className="m-lamp"
                          data-positive={v.tone === "positive" || undefined}
                          data-negative={v.tone === "negative" || undefined}
                          aria-hidden="true"
                        />
                        {v.word}
                      </span>
                      <p className="ta-verdict-note">{a.verdictNote}</p>
                    </div>
                  ) : (
                    <div className="m-well ta-untested" data-deep>
                      <span className="t-eyebrow">NO VERDICT · NOTHING RAN</span>
                      <p className="ta-verdict-note">{c.blockedBecause}</p>
                    </div>
                  )}

                  {a.trace.length > 0 && (
                    <>
                      <button
                        className="ta-trace-toggle"
                        aria-expanded={traceOpen}
                        onClick={() => setOpenTrace(traceOpen ? null : `${active.id}:${c.ref}`)}
                      >
                        <Icon name="chevron" size={12} className="ta-trace-caret" />
                        {traceOpen ? "hide the trace" : "the trace"}
                        {a.twinRunId && <span> · {a.twinRunId}</span>}
                      </button>

                      {traceOpen && (
                        <div className="m-well ta-trace vh-enter-fade" data-deep>
                          <ol>
                            {a.trace.map((s, i) => (
                              <li key={`${s.at}-${i}`}>
                                <span className="ta-trace-at">{s.at}</span>
                                <span className="ta-trace-what">{s.what}</span>
                              </li>
                            ))}
                          </ol>
                        </div>
                      )}
                    </>
                  )}
                </article>
              );
            })}

            {/* ------------------------------------------- primitive.diff */}
            <section className="ta-panel m-plate">
              <div className="ta-panel-head">
                <h3 className="t-eyebrow">
                  AGAINST {INCUMBENT.name.toUpperCase()}, WHO YOU ALREADY HAVE
                </h3>
                <span className="ta-col-note t-mono">{INCUMBENT.id}</span>
              </div>
              <table className="ta-diff">
                <caption className="vh-sr-only">
                  {active.name} compared with {INCUMBENT.name}, the colleague in this
                  district today
                </caption>
                <thead>
                  <tr>
                    <th scope="col">
                      <span className="t-eyebrow">WHAT</span>
                    </th>
                    <th scope="col">
                      <span className="t-eyebrow">TODAY</span>
                    </th>
                    <th scope="col">
                      <span className="t-eyebrow">WITH {active.name.toUpperCase()}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {active.diff.map((r) => (
                    <tr key={r.label}>
                      <th scope="row">
                        <span className="ta-diff-rowhead">
                          <span>{r.label}</span>
                          <span className="ta-diff-mark">
                            <span className="ta-diff-sign" aria-hidden="true">
                              {r.mark === "same" ? "=" : r.mark === "added" ? "+" : "~"}
                            </span>
                            {r.mark === "same" ? "unchanged" : r.mark === "added" ? "new" : "changed"}
                          </span>
                        </span>
                      </th>
                      <td data-col="today">{r.today}</td>
                      <td data-col={`with ${active.name}`}>{r.withThem}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="ta-note">
                {INCUMBENT.name} costs ₹{INCUMBENT.costPerMonthINR.toLocaleString("en-IN")} a
                month — {INCUMBENT.costBasis}. She is not replaced by anyone on this
                shortlist; the dispute work moves off her plate and her chases carry on.
              </p>
            </section>
          </div>

          {/* ---------------------------------------------------- the hire
              The only glass and the only gold on this surface. */}
          <section className="ta-hire m-glass" data-gold>
            <div className="ta-hire-head">
              <span className="m-medallion ta-hire-seal" aria-hidden="true">
                <Icon name="check" size={10} />
              </span>
              <span className="t-eyebrow" data-certified>
                CERTIFIED · {HIRE.act}
              </span>
            </div>

            {hired ? (
              <>
                <h3 className="ta-hire-title t-display">
                  {hired.name} is hired, at {HIRE.band}
                </h3>
                <div className="ta-hired" role="status">
                  <span className="m-lamp" data-positive aria-hidden="true" />
                  <span className="ta-hired-word">
                    on probation from today · {HIRE.probationDays} days
                  </span>
                </div>
                <p className="ta-band-means">{HIRE.probationMeans}</p>
                <p className="ta-passkey">
                  <Icon name="seal" size={12} />
                  The role is filled, so nothing further is offered here. Raising{" "}
                  {hired.name} above {HIRE.band} happens at confirmation, on the thirty
                  days you are about to watch.
                </p>
              </>
            ) : (
              <>
                <h3 className="ta-hire-title t-display">
                  Hire {active.name} at {HIRE.band}
                </h3>

                <div className="m-well ta-band">
                  <span className="ta-band-code">{HIRE.band}</span>
                  <span className="ta-band-means">{AUTONOMY_MEANS[HIRE.band]}</span>
                </div>

                <p className="ta-band-means">{HIRE.landsAtA1}</p>

                <div className="ta-hire-acts">
                  <button
                    className="m-btn m-metal-shine"
                    data-rank="certified"
                    onClick={() => {
                      setHiredId(active.id);
                      onEcho(`hired ${active.name} at ${HIRE.band}`);
                    }}
                  >
                    <Icon name="key" size={14} />
                    Hire {active.name} at {HIRE.band}
                  </button>
                  <button
                    className="m-btn"
                    data-rank="quiet"
                    onClick={() => onEcho(`opened ${active.name}’s charter to edit before hiring`)}
                  >
                    Edit the charter first
                  </button>
                </div>

                <p className="ta-passkey">
                  <Icon name="seal" size={12} />
                  {HIRE.passkeyNote}
                </p>
              </>
            )}
          </section>
        </div>
      </div>
    </section>
  );
}
