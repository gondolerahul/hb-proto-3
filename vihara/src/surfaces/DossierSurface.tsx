import { useState, type FormEvent } from "react";
import { Icon } from "../components/Icon";
import { Portrait } from "../components/Portrait";
import {
  AUTONOMY_MEANS,
  DOSSIERS,
  type Decision,
  type Dossier,
  type Proposal,
  type Slo,
} from "../fixtures/people";
import "./dossier.css";

/**
 * Colleague dossier / one-on-one · depth 2 · S (D6 §6).
 *
 * The surface finding RD-7 hit hardest: a *person* was rendered as a fallback.
 * Three decisions a reader could not infer from the code:
 *
 *  - **Recent decisions are told, not listed.** Each one is a paragraph in
 *    Pragya's narrative register with the trace exactly one flip away — the
 *    same relationship every narrative surface has to its data. A log teaches
 *    nothing; a sentence with a reason is a one-on-one.
 *  - **Feedback is an echo AND an input, and the UI says so.** What the owner
 *    types lands in the proposals list as `pending`, beside the colleague's own
 *    proposals, because SEGA's proposal path is the only door into a charter.
 *    Saying "this is a proposal, never a direct write" in the interface is a
 *    correctness statement, not copy.
 *  - **The dossier is a single measured column**, like the Tray — a one-on-one
 *    is read, not scanned. The only wide element is the charter/competency/SLO
 *    band, which is reference material rather than prose.
 *
 * Owner review C (2026-07-30) asked for colleagues to be more personified than
 * the abstract seal, so the portrait here is `components/Portrait` — art bible
 * §7 direction **A**, the halftone bust, generated rather than rastered. The
 * seal survives as direction C in `components/Seal`, which is what an entity
 * with no persona still gets: a gateway, a Meta-Agent role, a newly seeded
 * agent. Nothing is ever portrait-less.
 */

/* ========================================================================== */
/*  THE DOSSIER                                                               */
/* ========================================================================== */

const STANDING_LABEL: Record<Dossier["standing"], string> = {
  associate: "associate",
  probationer: "on probation",
  senior: "senior",
};

export function DossierSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const [activeId, setActiveId] = useState<string>(DOSSIERS[0]!.id);
  const [asGovernance, setAsGovernance] = useState(false);
  const [openTraces, setOpenTraces] = useState<Record<string, boolean>>({});
  const [draft, setDraft] = useState("");
  const [spoken, setSpoken] = useState<Record<string, Proposal[]>>({});

  const dossier = DOSSIERS.find((d) => d.id === activeId) ?? DOSSIERS[0]!;
  const proposals = [...dossier.proposals, ...(spoken[dossier.id] ?? [])];

  const speak = (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    const p: Proposal = {
      id: `P-${Date.now()}`,
      raised: "just now",
      asks: text,
      state: "pending",
      from: "you",
    };
    setSpoken((m) => ({ ...m, [dossier.id]: [...(m[dossier.id] ?? []), p] }));
    setDraft("");
    onEcho(`told ${dossier.name}: “${text}”`);
  };

  return (
    <section className="do">
      {/* -------------------------------------------------------- the roster */}
      <nav className="do-roster" aria-label="Colleagues">
        {DOSSIERS.map((d) => (
          <button
            key={d.id}
            className="do-roster-item"
            data-selected={d.id === dossier.id || undefined}
            onClick={() => setActiveId(d.id)}
          >
            <Portrait id={d.id} size={52} />
            <span className="do-roster-name">{d.name}</span>
          </button>
        ))}
      </nav>

      <div className="do-sheet vh-enter" key={dossier.id}>
        {/* ------------------------------------------------------- the head */}
        <header className="do-head m-plate m-ticks">
          <Portrait
            id={dossier.id}
            size={92}
            title={`${dossier.name} — a generated portrait, not a photograph`}
          />
          <div className="do-head-main">
            <span className="t-eyebrow">COLLEAGUE · {dossier.district.toUpperCase()}</span>
            <h1 className="do-name t-display">{dossier.name}</h1>
            <div className="do-head-chips">
              <span className="m-chip">{dossier.role}</span>
              <span className="m-chip">{STANDING_LABEL[dossier.standing]}</span>
              <span className="m-chip">{dossier.quarter}</span>
            </div>
            <p className="do-autonomy t-mono">
              {dossier.autonomy} — {AUTONOMY_MEANS[dossier.autonomy]}
            </p>
          </div>
          <div className="do-head-side">
            <span className="do-id t-mono">{dossier.id}</span>
            {dossier.handRaised && (
              <span className="do-hand">
                <span className="m-lamp" data-lit data-breathing />
                hand raised — in your tray
              </span>
            )}
            {dossier.doing && <span className="do-doing t-mono">now: {dossier.doing}</span>}
          </div>
        </header>

        {/* ------------------------------------------------- her own words */}
        <blockquote className="do-words">
          <p className="t-narrative">“{dossier.ownWords}”</p>
          <cite className="t-mono">— {dossier.name}, in her charter’s words</cite>
        </blockquote>

        {/* -------------------------------------------------- probation bar */}
        {dossier.probation && (
          <div className="do-probation m-well" role="status">
            <Icon name="clock" size={13} />
            <span className="t-mono">
              on probation · day {dossier.probation.dayOf} of {dossier.probation.days} · until{" "}
              {dossier.probation.until} · every act comes to your tray first
            </span>
          </div>
        )}

        {/* ------------------------------- charter · competencies · dials */}
        <div className="do-band">
          <section className="do-cell m-plate">
            <header className="do-cell-head">
              <h2 className="t-eyebrow">CHARTER</h2>
              <button
                className="m-chip"
                onClick={() => setAsGovernance((v) => !v)}
                aria-pressed={asGovernance}
              >
                <Icon name="ledger" size={12} />
                {asGovernance ? "in words" : "governance record"}
              </button>
            </header>
            {asGovernance ? (
              <div className="m-well do-gov-well" data-deep>
                <pre className="do-gov t-mono">{dossier.governance}</pre>
              </div>
            ) : (
              <dl className="do-charter">
                {dossier.charter.map((c) => (
                  <div className="do-clause" key={c.label}>
                    <dt className="t-eyebrow">{c.label.toUpperCase()}</dt>
                    <dd>{c.value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>

          <section className="do-cell m-plate">
            <header className="do-cell-head">
              <h2 className="t-eyebrow">
                COMPETENCIES · {dossier.competencies.filter((c) => c.kind === "tool").length} TOOLS ·{" "}
                {dossier.competencies.filter((c) => c.kind === "connector").length} CONNECTORS
              </h2>
            </header>
            <ul className="do-comps">
              {dossier.competencies.map((c) => (
                <li className="do-comp" key={c.name} data-withheld={c.withheld || undefined}>
                  <span className="do-comp-name t-mono">{c.name}</span>
                  <span className="do-comp-note">{c.note}</span>
                  {c.kind === "connector" && <span className="do-comp-kind t-mono">connector</span>}
                  {c.withheld && (
                    <span className="do-comp-withheld t-mono">
                      <Icon name="hold" size={11} />
                      withheld
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>

          <section className="do-cell m-plate">
            <header className="do-cell-head">
              <h2 className="t-eyebrow">SERVICE LEVEL · LAST {5} DAYS</h2>
            </header>
            <div className="do-slos">
              {dossier.slos.map((s) => (
                <SloDial key={s.label} slo={s} />
              ))}
            </div>
          </section>
        </div>

        {/* ------------------------------------------------------ decisions */}
        <section className="do-decisions">
          <header className="do-section-head">
            <h2 className="t-eyebrow">RECENT DECISIONS — TOLD, NOT LOGGED</h2>
            <hr className="m-rule-fade do-section-rule" />
          </header>
          <div className="vh-stagger">
            {dossier.decisions.map((d, i) => (
              <DecisionCard
                key={d.id}
                decision={d}
                index={i}
                open={!!openTraces[d.id]}
                onFlip={() => setOpenTraces((t) => ({ ...t, [d.id]: !t[d.id] }))}
              />
            ))}
          </div>
        </section>

        {/* ------------------------------------------------------ proposals */}
        <section className="do-proposals">
          <header className="do-section-head">
            <h2 className="t-eyebrow">PROPOSALS — WHERE FEEDBACK LANDS</h2>
            <hr className="m-rule-fade do-section-rule" />
          </header>
          {proposals.length === 0 ? (
            <p className="do-empty">
              Nothing is on the table. When you tell {dossier.name} something below, or she asks to
              change her own charter, it appears here as a proposal — the charter itself only ever
              changes by a certified act.
            </p>
          ) : (
            <ul className="do-proposal-list">
              {proposals.map((p) => (
                <li className="do-proposal m-plate" key={p.id}>
                  <span
                    className="m-lamp"
                    data-lit={p.state === "pending" || undefined}
                    data-positive={p.state === "certified" || undefined}
                  />
                  <div className="do-proposal-main">
                    <p className="do-proposal-asks">{p.asks}</p>
                    <span className="t-mono do-proposal-meta">
                      {p.id} · raised {p.raised} · by {p.from === "her" ? dossier.name : "you"}
                    </span>
                  </div>
                  <span className="do-proposal-state t-mono" data-state={p.state}>
                    {p.state === "pending" ? "pending your review" : p.state}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ----------------------------------------------------- tell input */}
        <form className="do-tell m-glass" onSubmit={speak}>
          <div className="do-tell-row">
            <input
              className="do-tell-input"
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={`Tell ${dossier.name} something…`}
              aria-label={`Tell ${dossier.name} something`}
            />
            <button className="m-btn do-tell-speak" type="submit" disabled={!draft.trim()}>
              <Icon name="forward" size={14} />
              Speak
            </button>
          </div>
          <p className="do-tell-note t-mono">
            What you say reaches her charter as a <strong>proposal</strong>, never a direct write —
            you will certify it before anything changes.
          </p>
        </form>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------- SLO dial -- */

/**
 * A 264° arc gauge. The needle position and the printed reading come from
 * separate fixture fields on purpose (`fill` vs `reading`) — the dial can
 * never quietly disagree with the number beside it. Meets/misses is a lamp
 * plus a word, never the arc's colour.
 */
function SloDial({ slo }: { slo: Slo }) {
  const SPAN = 264;
  const startDeg = 90 + (360 - SPAN) / 2; // gap centred at the bottom
  const tickAngle = ((startDeg + slo.target * SPAN) * Math.PI) / 180;
  const tick = {
    x1: +(40 + 25 * Math.cos(tickAngle)).toFixed(2),
    y1: +(40 + 25 * Math.sin(tickAngle)).toFixed(2),
    x2: +(40 + 35 * Math.cos(tickAngle)).toFixed(2),
    y2: +(40 + 35 * Math.sin(tickAngle)).toFixed(2),
  };
  return (
    <div className="do-slo">
      <div className="do-slo-dial">
        <svg width="80" height="80" viewBox="0 0 80 80" aria-hidden="true" focusable="false">
          <circle
            className="do-slo-track"
            cx="40"
            cy="40"
            r="30"
            pathLength={360}
            strokeDasharray={`${SPAN} ${360 - SPAN}`}
            transform={`rotate(${startDeg} 40 40)`}
          />
          <circle
            className="do-slo-fill"
            cx="40"
            cy="40"
            r="30"
            pathLength={360}
            strokeDasharray={`${slo.fill * SPAN} ${360 - slo.fill * SPAN}`}
            transform={`rotate(${startDeg} 40 40)`}
          />
          <line className="do-slo-tick" x1={tick.x1} y1={tick.y1} x2={tick.x2} y2={tick.y2} />
        </svg>
        <span className="do-slo-reading num">{slo.reading}</span>
      </div>
      <div className="do-slo-text">
        <span className="do-slo-label t-eyebrow">{slo.label.toUpperCase()}</span>
        <span className="do-slo-verdict">
          <span className="m-lamp" data-positive={slo.meets || undefined} data-negative={!slo.meets || undefined} />
          {slo.meets ? "meets" : "below"} · {slo.targetLabel}
        </span>
        <span className="do-slo-basis t-mono">{slo.basis}</span>
      </div>
    </div>
  );
}

/* -------------------------------------------------------- decision card -- */

function DecisionCard({
  decision,
  index,
  open,
  onFlip,
}: {
  decision: Decision;
  index: number;
  open: boolean;
  onFlip: () => void;
}) {
  return (
    <article className="do-decision m-plate" style={{ ["--i" as string]: index }}>
      <header className="do-decision-head">
        <span className="t-eyebrow">{decision.when.toUpperCase()}</span>
        <span className="t-mono do-decision-ref">{decision.ref}</span>
      </header>
      <p className="t-narrative do-decision-told">{decision.told}</p>
      <footer className="do-decision-foot">
        <button className="m-chip" onClick={onFlip} aria-expanded={open} data-selected={open || undefined}>
          <Icon name="chevron" size={12} className="do-flip-caret" data-open={open || undefined} />
          trace · {decision.id}
        </button>
        {/* A null cost renders as nothing. Never "₹0", never a dash. */}
        {decision.cost !== null && <span className="do-decision-cost t-mono">{decision.cost}</span>}
      </footer>
      {open && (
        <ol className="m-well do-trace vh-enter-fade" data-deep>
          {decision.steps.map((s, i) => (
            <li className="do-trace-step" key={i}>
              <span className="do-trace-at t-mono">{s.at}</span>
              <span className="do-trace-what t-mono">{s.what}</span>
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}
