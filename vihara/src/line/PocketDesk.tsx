import { useState } from "react";
import {
  LINE_PINS,
  READINGS,
  VITALS,
  type DeskDial,
  type DeskFigure,
  type DeskReading,
} from "../fixtures/pocket";
import "./desk.css";

/**
 * The Pocket Desk · the Line · C (D6 §16–18, R-3c C6).
 *
 * A person opens this on a phone to ask two things, in this order: **is anything
 * wrong, and what did I pin.** Everything here is one of those two answers, which
 * is why the Desk is not the Terrace made small. The estate's vitals live on a
 * map you walk; the pocket cannot be walked, so what crosses over is the handful
 * of readings that change the next minute — the estate's own sentence, the
 * raised hands, the pulse, the longest wait — and the map stays on the desk.
 *
 * Four decisions a reader would otherwise have to reverse-engineer.
 *
 * 1. **The band is the one piece of glass on this surface, and its readings sit
 *    in wells inside it.** Glass is for what floats over the world, so the cards
 *    scroll *under* the band rather than stopping short of it — which is the
 *    only thing that makes a pinned band read as pinned. "Readable over
 *    anything" is then a property of the composition rather than a claim about a
 *    blur radius: the sentence sits on the strong tint and every figure sits on
 *    an opaque `m-well`. Nothing else here is glass. The frame's rail and tab bar
 *    are docked, full-bleed and never overlapped by this slab, so the two layers
 *    never stack and never fog.
 *
 * 2. **A raised hand is not a fault.** "All is well." and "2 waiting on you" are
 *    both true at 21:00 on this Thursday, and the band carries them as two
 *    separate marks because the estate being healthy and the estate needing you
 *    are different questions the product distinguishes everywhere else. The
 *    hands mark is not a button: the way to them is the frame's own gold beacon
 *    on the Thread tab, and a second control that only changes tabs would teach
 *    that the tab bar is not the way. That mark is also the **only** gold on this
 *    surface, which is the rule `line.css` already sets for the frame.
 *
 * 3. **The young state is the primary state, so it is pinned on the first
 *    frame.** The KPI series starts 2026-07-25 with no backfill, and a card whose
 *    measure has produced no point renders **no figure at all** — never a zero,
 *    never a dash (§7.1). It gets a label, the reason, and where the record
 *    begins: a designed absence, not a hole. Beside it sits a measure that
 *    genuinely counted zero and prints `0`, because those two must never look
 *    alike.
 *
 * 4. **Pin and unpin are the surface's acts, and an empty desk is a designed
 *    state.** Both write `surface.line_pins` and both echo. With nothing pinned
 *    the column is prose explaining what pinning is for and what the band above
 *    does regardless — never a blank column, which reads as a surface that
 *    failed to load rather than as one you have not furnished yet.
 */
export function PocketDesk({ onEcho }: { onEcho: (msg: string) => void }) {
  /* Held here for the prototype; R-4 swaps in `fetchPreferences(LINE_PINS.key)`
     and writes each change back through `writePreference`. The surface already
     treats the pins as a stored, ordered list it does not own, so the swap is a
     loader rather than a rewrite. */
  const [pins, setPins] = useState<string[]>(LINE_PINS.value);

  /* The stored order is the owner's order, so the pins drive the list and the
     catalogue is whatever is left in the estate's own order. */
  const pinned = pins
    .map((id) => READINGS.find((r) => r.id === id))
    .filter((r): r is DeskReading => r !== undefined);
  const shelf = READINGS.filter((r) => !pins.includes(r.id));

  const hands = VITALS.handsRaised;
  const night = VITALS.hour >= 19 || VITALS.hour < 6;

  const move = (reading: DeskReading, onto: boolean) => {
    setPins((held) =>
      onto ? [...held, reading.id] : held.filter((id) => id !== reading.id),
    );
    onEcho(
      `${onto ? "pinned" : "unpinned"} ${nameOf(reading)} ${onto ? "to" : "from"} the pocket desk`,
    );
  };

  return (
    <section className="pd" aria-label="The pocket desk">
      {/* ============================================================ the vitals
          Never pinnable away, and never scrolled away either. */}
      <header className="pd-vitals m-glass" data-strong>
        <div className="pd-vitals-top">
          <span className="t-eyebrow">
            THE ESTATE · {night ? "NIGHT" : "DAY"} ·{" "}
            {String(VITALS.hour).padStart(2, "0")}:00
          </span>

          {/* The lamp is the fast read and the words are the correct one. */}
          <p className="pd-hands">
            <span
              className="m-lamp"
              data-lit={hands > 0 || undefined}
              data-breathing={hands > 0 || undefined}
            />
            <span className="pd-hands-word" data-lit={hands > 0 || undefined}>
              {hands > 0 ? `${hands} waiting on you` : "nothing waiting on you"}
            </span>
          </p>
        </div>

        {/* `narrative.still-line` — the estate's own sentence, and the title of
            this screen. The layout and the document outline say the same thing:
            the state of the estate is what you came here for. */}
        <h1 className="pd-still t-display">{VITALS.headline}</h1>

        <dl className="pd-strip">
          {VITALS.cells.map((cell) => (
            <div className="pd-cell m-well" key={cell.label}>
              <dt className="t-eyebrow">{cell.label}</dt>
              <dd className="pd-cell-figure num">{cell.figure}</dd>
            </div>
          ))}
        </dl>
      </header>

      {/* ============================================================ your pins */}
      {pinned.length === 0 ? (
        <div className="pd-empty m-plate" data-sunken>
          <span className="t-eyebrow">NOTHING PINNED</span>
          <p className="pd-empty-prose t-narrative">
            Nothing is pinned. The band above is the estate’s own state and it
            stays there whatever you choose — pinning is for the two or three
            readings you want in your pocket without walking the estate to find
            them.
          </p>
        </div>
      ) : (
        <section className="pd-section" aria-labelledby="pd-pinned">
          <h2 className="t-eyebrow" id="pd-pinned">
            PINNED
          </h2>
          <p className="pd-note t-mono">Vitals stay above whatever you pin.</p>

          <div className="pd-list vh-stagger">
            {pinned.map((reading, i) => (
              <PinnedCard
                key={reading.id}
                reading={reading}
                index={i}
                onUnpin={() => move(reading, false)}
              />
            ))}
          </div>
        </section>
      )}

      {/* ======================================================== the catalogue
          The pinned readings are objects; what is not pinned is a list of data,
          so it lives in a well rather than on six more plates. */}
      {shelf.length > 0 && (
        <section className="pd-section" aria-labelledby="pd-shelf">
          <h2 className="t-eyebrow" id="pd-shelf">
            NOT PINNED
          </h2>

          <ul className="pd-shelf m-well">
            {shelf.map((reading) => (
              <ShelfRow
                key={reading.id}
                reading={reading}
                onPin={() => move(reading, true)}
              />
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}

/** A dial is titled; a figure is labelled. Both are the reading's name, and the
 *  echo, the heading and the button's accessible name all use this one. */
function nameOf(reading: DeskReading): string {
  return reading.kind === "dial" ? reading.title : reading.label;
}

/**
 * Where the reading stands against its own target.
 *
 * The word is the carrier and the lamp only agrees with it (§4: never colour
 * alone) — which matters more here than usual, because "over target" is good on
 * a win rate and bad on a receivable, and only `betterWhen` knows which.
 */
function against(
  value: number,
  target: number,
  betterWhen: "lower" | "higher",
): "ahead" | "behind" | "on target" {
  if (value === target) return "on target";
  const ahead = betterWhen === "lower" ? value < target : value > target;
  return ahead ? "ahead" : "behind";
}

function PinnedCard({
  reading,
  index,
  onUnpin,
}: {
  reading: DeskReading;
  index: number;
  onUnpin: () => void;
}) {
  return (
    <article className="pd-card m-plate" style={{ ["--i" as string]: index }}>
      <header className="pd-card-head">
        <span className="t-eyebrow">{reading.where}</span>
        {/* The visible word is inside the accessible name, so a voice user and a
            sighted user reach for the same control. */}
        <button
          className="m-btn pd-act"
          data-rank="quiet"
          onClick={onUnpin}
          aria-label={`Unpin ${nameOf(reading)}`}
        >
          Unpin
        </button>
      </header>

      <h3 className="pd-card-title t-display">{nameOf(reading)}</h3>

      {reading.kind === "dial" ? (
        <DialBody dial={reading} />
      ) : (
        <FigureBody figure={reading} />
      )}
    </article>
  );
}

/**
 * `primitive.kpi-dial` at phone size: a figure, what it is measured against, and
 * how far it has come. No chart — five days of series is not a line, and drawing
 * one would be the same lie as inventing the number.
 */
function DialBody({ dial }: { dial: DeskDial }) {
  const { current, target, unit } = dial;

  /* Nothing in the series yet. One statement — the label, the reason, and where
     the record begins — and no meter and no trend beneath it, because three ways
     of saying the same absence would read as three faults. */
  if (current === null) {
    return (
      <Absent
        why={dial.absence}
        from={`Measured from ${dial.measuredFrom} · nothing before it was backfilled`}
      />
    );
  }

  const drift =
    target === null ? null : against(current.value, target.value, dial.betterWhen);
  const basis =
    drift === null || target === null
      ? dial.window
      : `${drift} · target ${target.value}${unit}`;

  return (
    <>
      <p className="pd-read">
        <span className="pd-figure t-figure num">
          {current.value}
          {/* The unit is set below the numeral's weight: it is what the number is
              in, not part of how big it is. */}
          {unit !== "" && <span className="pd-unit">{unit}</span>}
        </span>
      </p>

      {target !== null && drift !== null && (
        <Meter value={current.value} target={target.value} behind={drift === "behind"} />
      )}

      {basis !== null && (
        <Line
          text={basis}
          state={drift === null ? undefined : drift === "behind" ? "negative" : "positive"}
        />
      )}

      <Trend dial={dial} current={current.value} />
    </>
  );
}

/**
 * The move since the series began.
 *
 * There is no week-on-week here and there will not be one until October: with no
 * backfill, the only comparison a young series supports is against its own first
 * day. Where there is not even that, the slot says so in a sentence — a slot left
 * blank reads as a missing element, and a stated absence reads as the truth.
 */
function Trend({ dial, current }: { dial: DeskDial; current: number }) {
  const { since, unit } = dial;

  if (since === null) {
    return <Line text={`no earlier reading · the series starts ${dial.measuredFrom}`} />;
  }

  const moved = current - since.value;
  const better = dial.betterWhen === "lower" ? moved < 0 : moved > 0;

  /* Unmoved is neither good nor bad, so it keeps the unlit lamp and says
     "unchanged" rather than letting a colour decide for the reader. */
  if (moved === 0) return <Line text={`unchanged since ${since.on}`} />;

  return (
    <Line
      text={`${Math.abs(moved)}${unit} ${better ? "better" : "worse"} than ${since.on} · from ${since.value}${unit}`}
      state={better ? "positive" : "negative"}
    />
  );
}

/**
 * One instrument line under a figure: a lamp, then a sentence.
 *
 * Every line beneath a reading is built this way, lit or not, so the sentences
 * form one column down the card. Unlit, the lamp is that column's left edge and
 * nothing more — the same use the frame's own notice makes of it — and lit, the
 * word beside it always says the state as well (§4: never colour alone).
 */
function Line({ text, state }: { text: string; state?: "positive" | "negative" }) {
  return (
    <p className="pd-line">
      <span
        className="m-lamp"
        data-positive={state === "positive" || undefined}
        data-negative={state === "negative" || undefined}
      />
      <span className="t-mono">{text}</span>
    </p>
  );
}

/**
 * The reading against its target, as a rule with a mark on it rather than a
 * chart: one track, the distance travelled, the overshoot, and a hairline where
 * the target is.
 *
 * The three ratios arrive as custom properties. That is the same channel the
 * stagger index uses and the only one §1.4 leaves open — a measured proportion is
 * data, and the alternative is a width literal in the markup, which is
 * presentation. Nothing here animates.
 */
function Meter({
  value,
  target,
  behind,
}: {
  value: number;
  target: number;
  behind: boolean;
}) {
  /* Headroom above the larger of the two, as the district room's meter does it:
     a bar pinned to its own end reads as broken rather than as bad. */
  const max = Math.max(value, target) * 1.1;
  /* A zero measured against a zero has no scale to draw. It is a real reading and
     the figure above says so; the meter is what has nothing to add. */
  if (max <= 0) return null;

  const past = Math.max(0, value - target) / max;

  return (
    <div
      className="pd-meter"
      aria-hidden="true"
      style={{
        ["--pd-fill" as string]: Math.min(value, target) / max,
        ["--pd-past" as string]: past,
        ["--pd-tick" as string]: target / max,
      }}
    >
      <span className="pd-meter-fill" />
      {past > 0 && <span className="pd-meter-past" data-behind={behind || undefined} />}
      <span className="pd-meter-tick" />
    </div>
  );
}

/** `primitive.figure` — one number the wire already formatted, and one line of
 *  what it is of. No meter: a rupee amount here has no target to stand against,
 *  and a bar without one would be decoration. */
function FigureBody({ figure }: { figure: DeskFigure }) {
  if (figure.current === null) return <Absent why={figure.absence} from={null} />;

  return (
    <>
      <p className="pd-read">
        <span className="pd-figure t-figure num">{figure.current.figure}</span>
      </p>
      {figure.detail !== null && <Line text={figure.detail} />}
    </>
  );
}

/**
 * A reading that does not exist yet, drawn as a statement.
 *
 * The card keeps its shape — head, name, then this — so the young state is a
 * card that says something rather than a card missing its middle.
 */
function Absent({ why, from }: { why: string | null; from: string | null }) {
  /* §7.1 taken to its end: with no reason and no provenance there is nothing true
     to say, and nothing is what gets drawn. */
  if (why === null && from === null) return null;

  return (
    <div className="pd-absent">
      <span className="t-eyebrow">NO READING YET</span>
      {why !== null && <p className="pd-absent-why t-mono">{why}</p>}
      {from !== null && <p className="pd-absent-from t-mono">{from}</p>}
    </div>
  );
}

function ShelfRow({
  reading,
  onPin,
}: {
  reading: DeskReading;
  onPin: () => void;
}) {
  const figure = shelfFigure(reading);

  return (
    <li className="pd-shelf-row">
      <span className="pd-shelf-text">
        <span className="pd-shelf-title">{nameOf(reading)}</span>
        <span className="pd-shelf-where t-eyebrow">{reading.where}</span>
      </span>

      {/* No reading, no figure. Not a dash in the column, which a person reads as
          a zero (§7.1) — the card it becomes when pinned explains itself. */}
      {figure !== null && <span className="pd-shelf-figure num">{figure}</span>}

      <button
        className="m-btn pd-act"
        onClick={onPin}
        aria-label={`Pin ${nameOf(reading)}`}
      >
        Pin
      </button>
    </li>
  );
}

function shelfFigure(reading: DeskReading): string | null {
  if (reading.kind === "figure") {
    return reading.current === null ? null : reading.current.figure;
  }
  return reading.current === null ? null : `${reading.current.value}${reading.unit}`;
}
