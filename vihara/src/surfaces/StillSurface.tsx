import { COMPANY, DISTRICTS, STILL } from "../fixtures/estate";
import { Icon } from "../components/Icon";
import "./still.css";

/**
 * Depth 0 · the Still Surface (D6 §2).
 *
 * Finding **RD-4**: the first build read "no chrome, because it *is* the chrome"
 * as "nothing on screen" — three lines of text mid-page over black. A still
 * surface still has to be *composed*.
 *
 * What is added is not content, which would break L1's promise of stillness.
 * It is **composition**: a measured column at optical centre, a hairline that
 * gives the sentences an edge to sit against, the hour and the weather as the
 * quietest possible frame, and one gold line that is the only gold in the frame.
 * Everything here was already available to the first build — it just wasn't laid
 * out.
 *
 * The zero-gold-at-rest property (art bible §2.1) is preserved and testable:
 * with `handsRaised === 0` the only gold left is the brand mark.
 */
export function StillSurface({ onDescend }: { onDescend: () => void }) {
  const handsRaised = STILL.handsRaised;
  const totalSignals = DISTRICTS.reduce((n, d) => n + d.signalsPerHour, 0);
  const hour = COMPANY.localHour;
  const isNight = hour >= 19 || hour < 6;

  return (
    <section className="st" data-night={isNight || undefined}>
      {/* The hour, as the quietest possible frame. Not a clock — a horizon. */}
      <div className="st-frame" aria-hidden="true">
        <div className="st-horizon" />
      </div>

      <div className="st-column vh-stagger">
        <div className="st-eyebrow" style={{ ["--i" as string]: 0 }}>
          <span className="sh-mark st-mark" aria-hidden="true">
            <span className="sh-mark-dot" />
          </span>
          <span className="t-eyebrow">{COMPANY.name.toUpperCase()}</span>
          <span className="st-eyebrow-sep" aria-hidden="true" />
          <span className="t-eyebrow">
            {isNight ? "NIGHT" : "DAY"} · {String(hour).padStart(2, "0")}:00
          </span>
        </div>

        <h1 className="st-line st-line-head" style={{ ["--i" as string]: 1 }}>
          {STILL.headline}
        </h1>

        <p className="st-line" style={{ ["--i" as string]: 2 }}>
          <span className="num st-figure">₹{STILL.figure.collected}</span> collected
          this week.
        </p>

        {handsRaised > 0 ? (
          <p className="st-line st-line-gold" style={{ ["--i" as string]: 3 }}>
            <span className="m-lamp st-hand" data-lit data-breathing />
            {handsRaised === 1 ? "One colleague is" : `${handsRaised} colleagues are`}{" "}
            waiting for you.
          </p>
        ) : (
          <p className="st-line t-muted" style={{ ["--i" as string]: 3 }}>
            Nothing needs you.
          </p>
        )}

        <hr className="m-rule-fade st-rule" style={{ ["--i" as string]: 4 }} />

        {/* The pulse. One number, so the estate is visibly alive at rest. */}
        <div className="st-pulse" style={{ ["--i" as string]: 5 }}>
          <span className="st-pulse-dot" aria-hidden="true" />
          <span className="t-mono">
            {totalSignals} signals an hour · {DISTRICTS.length} quarters · all
            heartbeats answered
          </span>
        </div>

        <button className="st-descend" onClick={onDescend} style={{ ["--i" as string]: 6 }}>
          <span className="t-eyebrow">GO DEEPER</span>
          <span className="st-descend-keys t-mono">
            <kbd>⌘</kbd>
            <kbd>↓</kbd>
          </span>
          <Icon name="down" size={13} className="st-descend-icon" />
        </button>
      </div>
    </section>
  );
}
