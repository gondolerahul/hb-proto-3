import { useState, type FormEvent } from "react";
import { Icon } from "../components/Icon";
import {
  MATTER_SCRIPTS,
  UNTESTED_GRADE,
  scriptFor,
  type MatterScript,
} from "../fixtures/decisions";
import "./brainstorm.css";

/**
 * Tabling a matter — the owner-initiated half of the Boardroom.
 *
 * **Owner review D (2026-07-30):** *"How do I brainstorm here — say I am thinking
 * about developing a new marketing plan?"* The honest answer was that there was
 * no way to. The Boardroom only rendered propositions **Pragya** raised from KPI
 * drift; an owner arriving with a thought had nowhere to put it.
 *
 * What closes the gap is deliberately **not a chat panel**. It is the front of
 * the same pipeline: a matter you table becomes Minutes, the exchange becomes a
 * Proposition, and that Proposition adopts into a Resolution by the same
 * certified act as hers. A second way to make strategy would defeat STRAT's whole
 * premise, which is that there is one.
 *
 * The exchange has four beats, and each exists for a reason:
 *
 *  1. **She reads it back.** You see she understood the matter before she spends
 *     your attention on an answer to a different question.
 *  2. **She opens with what she knows** — named figures from the estate, not
 *     enthusiasm. A strategy conversation that begins with "great idea" has
 *     taught you nothing and cost you a turn.
 *  3. **She names what she cannot know**, and asks. Every question carries *why
 *     it is being asked* — what the answer changes — because a question without
 *     that is a form field.
 *  4. **The draft assembles as you answer**, in the Proposition idiom the rest of
 *     the surface already uses. It arrives `untested`, because nothing has been
 *     simulated; the Glasshouse is offered rather than a forecast implied.
 */

type Beat = "compose" | "reading" | "drafted";

export interface TabledMatter {
  matter: string;
  script: MatterScript;
  answers: Record<string, string>;
}

export function Brainstorm({
  onMinute,
  onTabled,
  onEcho,
}: {
  /** Every beat writes to the live minutes — the room is the record. */
  onMinute: (text: string, kind: "note" | "raised") => void;
  onTabled: (m: TabledMatter) => void;
  onEcho: (msg: string) => void;
}) {
  const [beat, setBeat] = useState<Beat>("compose");
  const [matter, setMatter] = useState("");
  const [script, setScript] = useState<MatterScript | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const table = (e: FormEvent) => {
    e.preventDefault();
    const text = matter.trim();
    if (!text) return;
    const s = scriptFor(text);
    setScript(s);
    setBeat("reading");
    onMinute(`You tabled: ${text}`, "note");
    onEcho(`tabled “${text}”`);
  };

  const answer = (q: string, label: string, sets: string) => {
    setAnswers((a) => ({ ...a, [q]: label }));
    onMinute(`${label} — ${sets}.`, "note");
  };

  const reset = () => {
    setBeat("compose");
    setMatter("");
    setScript(null);
    setAnswers({});
  };

  /* ------------------------------------------------------------- compose ---- */
  if (beat === "compose") {
    return (
      <section className="bs bs-compose m-plate" aria-label="Table a matter">
        <header className="bs-head">
          <span className="t-eyebrow">TABLE A MATTER</span>
          <p className="t-narrative bs-lead">
            Bring her something you are thinking about. She will tell you what she
            already knows, what she does not, and what she would need to turn it
            into a proposition you can adopt.
          </p>
        </header>

        <form className="bs-form" onSubmit={table}>
          <input
            className="bs-input"
            value={matter}
            onChange={(e) => setMatter(e.target.value)}
            placeholder="A marketing plan for the festive season…"
            aria-label="What would you like to table?"
          />
          <button className="m-btn" type="submit" disabled={!matter.trim()}>
            <Icon name="forward" size={14} />
            Table it
          </button>
        </form>

        <div className="bs-suggests">
          <span className="t-eyebrow">OR START FROM</span>
          {MATTER_SCRIPTS.map((s) => (
            <button
              key={s.match[0]}
              className="m-chip"
              onClick={() => {
                const seed = s.match[0] === "marketing" ? "A marketing plan for the festive season" : "Whether our pricing is right";
                setMatter(seed);
                const sc = scriptFor(seed);
                setScript(sc);
                setBeat("reading");
                onMinute(`You tabled: ${seed}`, "note");
                onEcho(`tabled “${seed}”`);
              }}
            >
              {s.match[0] === "marketing" ? "a marketing plan" : "our pricing"}
            </button>
          ))}
        </div>
      </section>
    );
  }

  if (!script) return null;
  const answered = script.questions.filter((q) => answers[q.id]).length;
  const allAnswered = answered === script.questions.length;

  /* --------------------------------------------------------------- drafted -- */
  if (beat === "drafted") {
    return (
      <section className="bs bs-drafted m-plate" data-raised aria-label="The drafted proposition">
        <header className="bs-head">
          <div className="bs-drafted-top">
            <span className="t-eyebrow">DRAFTED FROM YOUR MATTER</span>
            <button className="m-chip" onClick={reset}>
              <Icon name="undo" size={12} />
              table something else
            </button>
          </div>
          <h3 className="bs-draft-title t-display">{script.draft.title}</h3>
        </header>

        <blockquote className="bs-because">
          <p className="t-narrative">{script.draft.because}</p>
          <cite className="t-mono">— Pragya, from what you told her</cite>
        </blockquote>

        {/* She states the objection to her own draft. A proposition that argues
            only for itself is advocacy, and an owner cannot weigh advocacy. */}
        <div className="m-well bs-concerns">
          <span className="t-eyebrow">WHAT WOULD WORRY ME</span>
          <p className="t-narrative bs-concerns-body">{script.draft.concerns}</p>
        </div>

        {script.draft.levers.length > 0 && (
          <ul className="bs-levers">
            {script.draft.levers.map((l) => (
              <li className="bs-lever" key={l.label}>
                <span>{l.label}</span>
                <span className="bs-lever-vals">
                  <span className="bs-lever-from">{l.from}</span>
                  <span className="bs-lever-arrow">→</span>
                  <span className="bs-lever-to">{l.to}</span>
                </span>
              </li>
            ))}
          </ul>
        )}

        {/* `expected` is null on both scripts, and that is the point: nothing
            projects an effect for a first-of-its-kind act. A null renders as no
            line at all — never as a zero, never as a dash. */}
        {script.draft.expected && (
          <p className="bs-expected">
            <Icon name="trend" size={14} className="bs-expected-icon" />
            {script.draft.expected.label}{" "}
            <span className="bs-expected-val">{script.draft.expected.value}</span>
          </p>
        )}

        <div className="m-well bs-grade" data-deep>
          <div className="br-grade" data-grade={UNTESTED_GRADE.grade}>
            <span className="br-grade-mark" aria-hidden="true" />
            <span className="br-grade-word t-eyebrow">untested · never tried</span>
            <span className="br-grade-strip" aria-hidden="true" />
            <span className="br-grade-run t-mono">no run behind it</span>
            <p className="br-grade-means t-mono">{UNTESTED_GRADE.means}</p>
          </div>
        </div>

        <div className="bs-acts">
          <button
            className="m-btn"
            data-rank="certified"
            onClick={() => {
              onMinute(
                `${script.draft.title} adopted as ${script.draft.resolutionId}.`,
                "raised",
              );
              onEcho(`adopted resolution ${script.draft.resolutionId}`);
              reset();
            }}
          >
            <Icon name="key" size={14} />
            Adopt as Resolution
          </button>
          <button className="m-btn bs-gh" data-rank="quiet" disabled>
            <Icon name="seal" size={13} />
            Take to the Glasshouse
          </button>
        </div>
        <p className="bs-gh-note t-mono">
          The Glasshouse would grade this before you commit. Its scenario runner is
          not wired end-to-end yet, so the button is drawn and not live — you are
          seeing a real gap, not a real feature.
        </p>
      </section>
    );
  }

  /* --------------------------------------------------------------- reading -- */
  return (
    <section className="bs bs-reading m-plate" aria-label="Pragya's read on the matter">
      <header className="bs-head">
        <div className="bs-drafted-top">
          <span className="t-eyebrow">
            <span className="m-lamp bs-lamp" data-lit data-breathing />
            SHE IS THINKING WITH YOU
          </span>
          <button className="m-chip" onClick={reset}>
            <Icon name="close" size={12} />
            drop it
          </button>
        </div>
        <p className="t-narrative bs-reading-lead">{script.reading}</p>
      </header>

      {script.knows.length > 0 && (
        <div className="bs-block">
          <span className="t-eyebrow">WHAT I ALREADY KNOW</span>
          <ul className="bs-knows">
            {script.knows.map((k) => (
              <li className="bs-know" key={k.label}>
                <span className="bs-know-figure">{k.value}</span>
                <span className="bs-know-text">
                  <span className="bs-know-label t-eyebrow">{k.label}</span>
                  <span className="bs-know-note">{k.note}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="bs-block">
        <span className="t-eyebrow">WHAT I DO NOT HAVE</span>
        <ul className="bs-missing">
          {script.missing.map((m) => (
            <li className="bs-miss" key={m}>
              <span className="m-lamp" />
              <span>{m}</span>
            </li>
          ))}
        </ul>
      </div>

      <hr className="m-rule-fade" />

      <div className="bs-block">
        <div className="bs-q-head">
          <span className="t-eyebrow">WHAT I NEED FROM YOU</span>
          <span className="t-mono bs-progress">
            {answered} of {script.questions.length}
          </span>
        </div>

        <ol className="bs-questions">
          {script.questions.map((q, i) => (
            <li className="bs-question" key={q.id} data-answered={answers[q.id] ? true : undefined}>
              <p className="bs-asks">{q.asks}</p>
              {/* Why she is asking. A question without this is a form field. */}
              <p className="bs-because-note t-mono">{q.because}</p>
              <div className="bs-options">
                {q.options.map((o) => (
                  <button
                    key={o.label}
                    className="m-chip"
                    data-selected={answers[q.id] === o.label || undefined}
                    onClick={() => answer(q.id, o.label, o.sets)}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
              {answers[q.id] && (
                <p className="bs-answered t-mono">
                  <Icon name="check" size={11} />
                  {q.options.find((o) => o.label === answers[q.id])?.sets}
                </p>
              )}
              {i < script.questions.length - 1 && <hr className="m-rule" />}
            </li>
          ))}
        </ol>
      </div>

      <div className="bs-acts">
        <button
          className="m-btn"
          disabled={!allAnswered}
          onClick={() => {
            setBeat("drafted");
            onTabled({ matter, script, answers });
            onMinute(`${script.draft.title} raised as a proposition.`, "raised");
            onEcho("raised a proposition from your matter");
          }}
        >
          <Icon name="record" size={14} />
          {allAnswered ? "Draft the proposition" : `Answer ${script.questions.length - answered} more`}
        </button>
      </div>
    </section>
  );
}
