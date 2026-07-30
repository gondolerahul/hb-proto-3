import { useCallback, useEffect, useState } from "react";
import { Icon } from "../components/Icon";
import { Portrait } from "../components/Portrait";
import { GradeSeal } from "./BoardroomSurface";
import { STANDUP, STANDUP_DAY, type StandupLine } from "../fixtures/decisions";
import "./standup.css";

/**
 * The Standup · depth 1–2 · C sequence (D6 §10).
 *
 * Ninety seconds, one card per colleague, each drillable. On the Line this same
 * surface *is* the Morning Story.
 *
 * **The rule that shapes everything here is L2: every line is relayed by Pragya,
 * never spoken by the colleague.** One voice is not a stylistic preference — it
 * is what keeps notification discipline enforceable, because a tenant who can be
 * addressed by twelve colleagues has twelve channels to mute and will mute the
 * wrong one. So:
 *
 *  - the prose is hers, in the third person, and the card says *prepared by* whom
 *    rather than putting words in their mouth;
 *  - a colleague's own output appears only as **facts** — labelled data below the
 *    line, never as a quote.
 *
 * Two densities, and a real toggle, because the spec asks for genuinely different
 * things rather than the same layout at two sizes:
 *
 *  - **novice** — a sequence. One card at a time, ninety seconds, arrow-keyed,
 *    with a progress rail. This is the register a morning briefing has.
 *  - **operator** — all lines on one sheet, scannable, voice off. This is the
 *    register a person who already knows their estate wants.
 */

type Density = "novice" | "operator";

export function StandupSurface({
  onOpenTray,
  onOpenDossier,
  onEcho,
}: {
  onOpenTray?: () => void;
  onOpenDossier?: (id: string) => void;
  onEcho: (msg: string) => void;
}) {
  const [density, setDensity] = useState<Density>("novice");
  const [at, setAt] = useState(0);
  const line = STANDUP[at];

  const step = useCallback(
    (by: number) => {
      setAt((i) => {
        const next = Math.min(STANDUP.length - 1, Math.max(0, i + by));
        const l = STANDUP[next];
        if (l && next !== i) onEcho(`opened ${l.who.name}’s standup line`);
        return next;
      });
    },
    [onEcho],
  );

  useEffect(() => {
    if (density !== "novice") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey) return;
      if (e.key === "ArrowRight") step(1);
      if (e.key === "ArrowLeft") step(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [density, step]);

  const waiting = STANDUP.filter((l) => l.needsYou).length;

  return (
    <section className="su" data-density={density}>
      {/* ------------------------------------------------------------- header */}
      <header className="su-head">
        <div className="su-head-lead">
          <span className="t-eyebrow">
            THE STANDUP · {STANDUP_DAY.label.toUpperCase()} · COVERING{" "}
            {STANDUP_DAY.covering.toUpperCase()}
          </span>
          <h1 className="su-title t-display">
            {STANDUP.length} colleagues, {STANDUP_DAY.budgetSeconds} seconds
          </h1>
          {/* L2 said in words, on the surface, not only in the code. */}
          <p className="su-voice t-mono">
            <span className="m-lamp" data-lit />
            Every line below is Pragya’s. Your colleagues prepare them; she is the
            only one who speaks.
          </p>
        </div>

        <div className="su-head-side">
          {waiting > 0 && (
            <button className="m-chip su-waiting" onClick={onOpenTray}>
              <span className="m-lamp" data-lit data-breathing />
              {waiting} waiting on you
            </button>
          )}
          <div className="su-density" role="radiogroup" aria-label="Density">
            <span className="t-eyebrow">DENSITY</span>
            {(["novice", "operator"] as const).map((d) => (
              <button
                key={d}
                role="radio"
                aria-checked={density === d}
                className="m-chip"
                data-selected={density === d || undefined}
                onClick={() => setDensity(d)}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* =============================================== novice — the sequence */}
      {density === "novice" && line && (
        <>
          <div className="su-stage">
            <StandupCard
              line={line}
              onOpenTray={onOpenTray}
              onOpenDossier={onOpenDossier}
              expanded
            />
          </div>

          <footer className="su-rail">
            <button
              className="m-btn"
              data-rank="quiet"
              onClick={() => step(-1)}
              disabled={at === 0}
              aria-label="Previous colleague"
            >
              <Icon name="back" size={14} />
            </button>

            <ol className="su-pips">
              {STANDUP.map((l, i) => (
                <li key={l.id}>
                  <button
                    className="su-pip"
                    data-active={i === at || undefined}
                    data-passed={i < at || undefined}
                    onClick={() => setAt(i)}
                    aria-label={`${l.who.name}, line ${i + 1} of ${STANDUP.length}`}
                    aria-current={i === at ? "true" : undefined}
                  >
                    {l.needsYou && <span className="su-pip-hand" aria-hidden="true" />}
                  </button>
                </li>
              ))}
            </ol>

            <span className="su-count t-mono">
              {at + 1} of {STANDUP.length}
            </span>

            <button
              className="m-btn"
              onClick={() => step(1)}
              disabled={at === STANDUP.length - 1}
            >
              Next
              <Icon name="forward" size={14} />
            </button>
          </footer>
        </>
      )}

      {/* ============================================= operator — one sheet */}
      {density === "operator" && (
        <div className="su-sheet vh-stagger">
          {STANDUP.map((l, i) => (
            <div key={l.id} style={{ ["--i" as string]: i }}>
              <StandupCard line={l} onOpenTray={onOpenTray} onOpenDossier={onOpenDossier} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function StandupCard({
  line,
  expanded = false,
  onOpenTray,
  onOpenDossier,
}: {
  line: StandupLine;
  expanded?: boolean;
  onOpenTray?: () => void;
  onOpenDossier?: (id: string) => void;
}) {
  return (
    <article className="su-card m-plate" data-expanded={expanded || undefined} key={line.id}>
      <header className="su-card-head">
        <button
          className="su-who"
          onClick={() => onOpenDossier?.(line.who.id)}
          aria-label={`Open ${line.who.name}’s dossier`}
        >
          <div className="m-portrait-well su-portrait">
            <Portrait id={line.who.id} size={expanded ? 60 : 42} />
          </div>
          <span className="su-who-text">
            <span className="su-who-name t-display">{line.who.name}</span>
            <span className="t-mono su-who-meta">
              {line.who.role} · {line.who.id}
            </span>
          </span>
        </button>

        {/* Attribution, not authorship. The card says who prepared it; the words
            are hers. */}
        <span className="su-prepared t-mono">
          prepared by {line.who.name} · {line.preparedAt}
        </span>
      </header>

      <p className="su-line t-narrative">{line.line}</p>

      {/* The colleague's own output, as data — never as a quote (L2). */}
      <dl className="m-well su-facts">
        {line.facts.map((f) => (
          <div className="su-fact" key={f.label}>
            <dt className="t-eyebrow">{f.label}</dt>
            <dd className="t-mono su-fact-val">{f.value}</dd>
          </div>
        ))}
      </dl>

      <div className="su-card-foot">
        {/* `moved` is null where nothing moved or nothing measured it. Renders as
            nothing — never as "0" and never as "no change", which would claim a
            measurement that was not taken. */}
        {line.moved && (
          <span className="su-moved">
            <Icon name="trend" size={13} className="su-moved-icon" />
            <span className="t-mono">{line.moved.label}</span>
            <span className="su-moved-val">{line.moved.value}</span>
          </span>
        )}

        {line.grade && <GradeSeal grade={line.grade} compact />}

        {line.needsYou && (
          <button className="m-btn su-needs" data-rank="certified" onClick={onOpenTray}>
            <Icon name="key" size={13} />
            {line.needsYou.ask}
          </button>
        )}
      </div>
    </article>
  );
}
