import { useState } from "react";
import { Icon } from "../components/Icon";
import {
  AGENDA,
  BOARD,
  MINUTES,
  PROPOSITIONS,
  type AgendaItem,
  type Grade,
  type Minute,
  type Proposition,
} from "../fixtures/decisions";
import "./boardroom.css";

/**
 * The Boardroom · depth 2 · S (+W setting) (D6 §8).
 *
 * Nothing in the platform produces Planning records today; this room is the
 * missing producer, and the minutes column says so in mono rather than
 * pretending a Planning Hall already filled it.
 *
 * Three decisions a reader could not reverse-engineer from the markup:
 *
 *  - **The four honesty grades are told apart by form, not hue.** Under the
 *    §2.1 gold budget four status colours were never on the table, so each
 *    grade is a shape + a texture + the engine's own sentence: `replay` is a
 *    struck (filled) square over a solid strip; `forecast` a dashed square
 *    over a dashed strip; `unknown` a slashed square over a broken strip; and
 *    `untested` is a hollow CIRCLE with no strip and no run id — the only
 *    grade with nothing behind it, rendered as deliberate absence rather than
 *    as a fault. The circle-vs-square split keeps untested and unknown apart
 *    in greyscale and at a squint, before a single word is read. `GradeSeal`
 *    is exported and the Standup imports it, so the family cannot drift into
 *    two idioms for its most important distinction.
 *  - **Adoption speaks the Tray's certified grammar**, not a new one: gold
 *    metal button, key icon, frozen-component note, medallion once struck.
 *    Adopting also mints a minute in the live column at that moment — the
 *    surface performs the producer role it claims to be.
 *  - **"Take to Glasshouse" is drawn disabled with its reason beside it.**
 *    TWIN's scenario runner is not wired end-to-end; a live-looking button
 *    over that gap is the exact dishonesty D4 §3.1 exists to prevent.
 */

const GRADE_WORD: Record<Grade["grade"], string> = {
  replay: "replay",
  forecast: "forecast",
  untested: "untested · never tried",
  unknown: "unknown · could not be graded",
};

/**
 * The family's grade idiom, in one place. `compact` renders only the mark and
 * the word — for closed card heads, where the full sentence would shout.
 */
export function GradeSeal({ grade, compact = false }: { grade: Grade; compact?: boolean }) {
  return (
    <div className="br-grade" data-grade={grade.grade} data-compact={compact || undefined}>
      <span className="br-grade-mark" aria-hidden="true" />
      <span className="br-grade-word t-eyebrow">{GRADE_WORD[grade.grade]}</span>
      {!compact && (
        <>
          {/* For `untested` this strip stays empty on purpose: there is no run
              to draw a texture of. The blank is the idiom. */}
          <span className="br-grade-strip" aria-hidden="true" />
          <span className="br-grade-run t-mono">
            {grade.twinRunId !== null ? grade.twinRunId : "no run behind it"}
          </span>
          <p className="br-grade-means t-mono">{grade.means}</p>
        </>
      )}
    </div>
  );
}

const DRIFT: Record<
  AgendaItem["drift"],
  { word: string; lamp: "negative" | "positive" | "lit" | "plain" }
> = {
  behind: { word: "Behind", lamp: "negative" },
  ahead: { word: "Ahead", lamp: "positive" },
  flat: { word: "Flat", lamp: "plain" },
  flagged: { word: "Flagged", lamp: "lit" },
  /* An honest absence, so it gets the unlit lamp — the same family logic as
     the untested grade: absence is not a fault state. */
  "no-comparison": { word: "No comparison yet", lamp: "plain" },
};

export function BoardroomSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const [openId, setOpenId] = useState<string>(PROPOSITIONS[0]!.id);
  const [adopted, setAdopted] = useState<Record<string, string>>({});
  const [minutes, setMinutes] = useState<Minute[]>(MINUTES);

  const adopt = (p: Proposition) => {
    setAdopted((a) => ({ ...a, [p.id]: p.resolutionId }));
    /* The resolution id is minted by the adopt call (pre-bound in the fixture)
       and only ever shown after the act — never before. */
    setMinutes((m) => [
      ...m,
      {
        id: `MIN-${m.length + 1}`,
        at: "now",
        text: `${p.id} adopted as ${p.resolutionId}. ${p.title}.`,
        kind: "resolution",
      },
    ]);
    onEcho(`adopted resolution ${p.resolutionId}`);
    const next = PROPOSITIONS.find((q) => q.id !== p.id && !adopted[q.id]);
    if (next) setOpenId(next.id);
  };

  return (
    <section className="br">
      {/* ------------------------------------------------------------- header */}
      <header className="br-head">
        <div>
          <span className="t-eyebrow">
            THE BOARDROOM · {BOARD.sitting} · {BOARD.period}
          </span>
          <h1 className="br-title t-display">{BOARD.title}</h1>
        </div>
        <div className="br-head-meta">
          <span className="m-chip">
            <Icon name="clock" size={12} />
            opened {BOARD.openedAt}
          </span>
          <span className="br-listening" role="status">
            {/* Gold sanctioned here: Pragya's beam while she narrates/minutes. */}
            <span className="m-lamp" data-lit data-breathing />
            <span className="t-mono">Pragya is listening</span>
          </span>
        </div>
      </header>

      <div className="br-body">
        <div className="br-main vh-stagger">
          {/* ------------------------------------------- she arrives prepared */}
          <section
            className="br-agenda m-plate m-ticks"
            aria-label="Agenda, drawn from KPI drift"
            style={{ ["--i" as string]: 0 }}
          >
            <header className="br-block-head">
              <span className="t-eyebrow">SHE ARRIVES PREPARED</span>
              <span className="br-block-note t-mono">
                drawn from KPI drift · the series began {BOARD.seriesStartsOn}, no backfill
              </span>
            </header>
            <ul className="br-agenda-list">
              {AGENDA.map((a) => {
                const d = DRIFT[a.drift];
                return (
                  <li className="br-agenda-item" key={a.label}>
                    <span className="br-agenda-state">
                      {/* Lamp + word, never colour alone. */}
                      <span
                        className="m-lamp"
                        data-negative={d.lamp === "negative" || undefined}
                        data-positive={d.lamp === "positive" || undefined}
                        data-lit={d.lamp === "lit" || undefined}
                      />
                      <span className="br-agenda-word t-eyebrow">{d.word}</span>
                      {/* A null delta renders nothing. Never 0, never a dash. */}
                      {a.delta !== null && <span className="br-agenda-delta t-mono">{a.delta}</span>}
                    </span>
                    <span className="br-agenda-text">
                      <span className="br-agenda-label t-display">{a.label}</span>
                      <span className="br-agenda-detail">{a.detail}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>

          {/* ------------------------------------------------- the propositions */}
          <section className="br-props" aria-label="Propositions" style={{ ["--i" as string]: 1 }}>
            <header className="br-block-head">
              <span className="t-eyebrow">PROPOSITIONS</span>
              <span className="br-block-note t-mono">
                {PROPOSITIONS.length} tabled · graded before you bet · four grades, not three
              </span>
            </header>

            <div className="br-props-list">
              {PROPOSITIONS.map((p) => (
                <PropositionCard
                  key={p.id}
                  prop={p}
                  open={openId === p.id && !adopted[p.id]}
                  adoptedAs={adopted[p.id]}
                  onOpen={() => setOpenId(p.id)}
                  onAdopt={() => adopt(p)}
                />
              ))}
            </div>
          </section>
        </div>

        {/* -------------------------------------------------- the live minutes */}
        <aside className="br-minutes m-well" data-deep aria-label="Minutes, accruing live">
          <header className="br-minutes-head">
            <span className="t-eyebrow">MINUTES</span>
            <span className="br-minutes-live t-mono">accruing as you speak</span>
          </header>
          <ol className="br-minutes-list" aria-live="polite">
            {minutes.map((m) => (
              <li className="br-minute" key={m.id} data-kind={m.kind}>
                <span className="br-minute-at t-mono">{m.at}</span>
                <span className="br-minute-mark" aria-hidden="true" />
                <p className="br-minute-text t-mono">{m.text}</p>
              </li>
            ))}
          </ol>
          <hr className="m-rule-fade" />
          <footer className="br-minutes-foot">
            <button
              className="m-btn"
              data-rank="quiet"
              onClick={() => onEcho("crossed to the planning hall")}
            >
              <Icon name="ledger" size={13} />
              Planning Hall
            </button>
            <p className="br-minutes-note t-mono">
              nothing else produces Planning records today — this room is the producer
            </p>
          </footer>
        </aside>
      </div>
    </section>
  );
}

function PropositionCard({
  prop,
  open,
  adoptedAs,
  onOpen,
  onAdopt,
}: {
  prop: Proposition;
  open: boolean;
  adoptedAs: string | undefined;
  onOpen: () => void;
  onAdopt: () => void;
}) {
  if (adoptedAs) {
    return (
      <article className="br-prop br-prop-adopted m-plate">
        <span className="m-medallion br-adopt-seal" aria-hidden="true">
          {/* Same struck check as the Tray's certified seal — one grammar. */}
          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#2a1d08" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </span>
        <span className="br-adopted-text">{prop.title}</span>
        <span className="t-eyebrow" data-certified>
          ADOPTED · {adoptedAs}
        </span>
      </article>
    );
  }

  return (
    <article className="br-prop m-plate" data-open={open || undefined}>
      <button className="br-prop-head" onClick={onOpen} aria-expanded={open}>
        <span className="br-prop-lead">
          <span className="br-prop-id t-mono">{prop.id}</span>
          <h3 className="br-prop-title t-display">{prop.title}</h3>
        </span>
        <span className="br-prop-right">
          <GradeSeal grade={prop.grade} compact />
          <span className="br-prop-at t-mono">raised {prop.raisedAt}</span>
          <Icon name="chevron" size={14} className="br-caret" />
        </span>
      </button>

      {open && (
        <div className="br-prop-body vh-enter-fade">
          {/* Her case for it — one voice, hers, with the concern it touches. */}
          <blockquote className="br-because">
            <p className="t-narrative">{prop.because}</p>
            <cite className="t-mono">— Pragya · {prop.concerns}</cite>
          </blockquote>

          {/* The levers, set into a well: this is the data of the bet. */}
          <div className="m-well br-levers" data-deep>
            <dl>
              {prop.levers.map((l) => (
                <div className="br-lever" key={l.label}>
                  <dt className="t-eyebrow">{l.label}</dt>
                  <dd className="br-lever-vals">
                    <span className="t-mono br-lever-from">{l.from}</span>
                    <Icon name="forward" size={12} className="br-lever-arrow" />
                    <span className="t-mono br-lever-to">{l.to}</span>
                  </dd>
                </div>
              ))}
            </dl>
          </div>

          {/* A null expectation renders nothing at all — never "₹0", never a
              dash. A board that always sees a number learns every bet has one. */}
          {prop.expected && (
            <p className="br-expected">
              <Icon name="trend" size={13} className="br-expected-icon" />
              <span className="t-eyebrow">EXPECTED</span>
              <span className="t-mono br-expected-val">
                {prop.expected.label} · {prop.expected.value}
              </span>
            </p>
          )}

          <div className="m-well br-grade-well">
            <GradeSeal grade={prop.grade} />
          </div>

          <div className="br-acts">
            <button className="m-btn" data-rank="certified" onClick={onAdopt}>
              <Icon name="key" size={14} />
              Adopt as Resolution
            </button>
            <span className="br-glasshouse">
              <button className="m-btn br-gh-btn" data-rank="quiet" disabled>
                <Icon name="forward" size={13} />
                Take to Glasshouse
              </button>
              <span className="br-glasshouse-note t-mono">
                drawn, not live — TWIN's scenario runner is not wired end-to-end
              </span>
            </span>
          </div>

          <p className="br-cert-note t-mono">
            <Icon name="seal" size={12} />
            Adoption is a certified act — certified.strategy-resolution@1, T2. It is
            rendered from a frozen component, never from a manifest, and it will ask
            for your passkey.
          </p>
        </div>
      )}
    </article>
  );
}
