import { useState } from "react";
import type { EstateSnapshot, EstateTreasury, PlinthKpi } from "../api/estate";
import { fetchKpiHistory, type KpiSeries } from "../api/gallery";
import { fetchPreferences, writePreference, type PreferenceValue } from "../api/study";
import type { WireState } from "../estate/sharedStream";
import { useLiveEstate } from "../estate/useLiveEstate";
import { Bar, Empty, Failed, Lines, Scaffold, useResource } from "../lifecycle";
import { stillLine } from "../surfaces/StillSurface";
import "./desk.css";

/**
 * The Pocket Desk · the Line · C (D6 §16–18, R-3c C6) — on the live estate,
 * `/ai/kpi/history` and `surface.line_pins` (R-4 part W).
 *
 * A person opens this on a phone to ask two things, in this order: **is anything
 * wrong, and what did I pin.** Everything here is one of those two answers, which
 * is why the Desk is not the Terrace made small. The estate's vitals live on a
 * map you walk; the pocket cannot be walked, so what crosses over is the handful
 * of readings that change the next minute — the estate's own sentence, the
 * raised hands, the pulse, the soonest decision — and the map stays on the desk.
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
 *    both true at once, and the band carries them as two separate marks because
 *    the estate being healthy and the estate needing you are different questions
 *    the product distinguishes everywhere else. The hands mark is not a button:
 *    the way to them is the frame's own gold beacon on the Thread tab, and a
 *    second control that only changes tabs would teach that the tab bar is not
 *    the way. That mark is also the **only** gold on this surface, which is the
 *    rule `line.css` already sets for the frame.
 *
 * 3. **The young state is the primary state.** The KPI series starts with no
 *    backfill (D6 §11), and `estate.py` puts **every** KPI definition on a
 *    district's plinth whether or not a snapshot has ever been taken for it — so
 *    a fresh tenant's Desk is mostly measures with no reading. A card whose
 *    measure has produced no point renders **no figure at all** — never a zero,
 *    never a dash (§7.1). It gets a label, the reason, and where the record
 *    begins: a designed absence, not a hole. Beside it, a measure that genuinely
 *    counted zero prints `0`, because those two must never look alike. That is
 *    the whole distinction between `value: null` and `value: 0` on the wire, and
 *    the projection is careful to keep them apart; so is this.
 *
 * 4. **Pin and unpin are the surface's acts, and both are writes.** They put
 *    `surface.line_pins` through LEARN's preference store and only echo when the
 *    store took it. A pin that echoed and did not persist is the exact fraud
 *    part C names — a control that looks kept and is forgotten — so a failed
 *    write puts the reading back where it was and says so, and nothing is
 *    announced that did not happen.
 *
 * ## What the wiring removed, and why it is not a redesign
 *
 * **The meter is gone, and no target replaced it.** The card drew a rule with a
 * mark on it: the reading, the overshoot, and a hairline where the target was.
 * **There is no target anywhere on the platform** — `KpiDefinition` declares a
 * baseline, a formula and a unit, and no target and no direction, which is the
 * same finding that keeps `fog` off the estate's weather vocabulary and killed
 * the Dossier's three arc gauges. A meter can only be drawn to a number, so the
 * only number available was one this file chose. It is deleted rather than
 * rescaled.
 *
 * **And with the direction went the sage and terracotta on the trend.** "Six
 * days better" is a judgement that needs to know whether lower is better, and
 * nothing on the wire says. The move is still reported — it is a measurement —
 * but it is reported as up or down with an unlit lamp, because a colour that
 * decides for the reader which way is good is inventing the half of the fact the
 * platform does not hold.
 *
 * **The band's money cell went with them.** "Collected this week" had no binding
 * on the estate projection at all. What stands in its place is the first measure
 * the estate can actually answer — the same slot, the same question, and the
 * projection's own display name on it — and where nothing is measurable yet the
 * cell is absent rather than filled.
 */

/** LEARN's key for this surface's pins. The namespace already exists, so a pin
 *  is a code-reviewed key rather than a new table (LINE §6). */
const LINE_PINS_KEY = "surface.line_pins";

/* ------------------------------------------------------------- the readings */

interface ReadingBase {
  /** What is written into `surface.line_pins`. For a dial it is the KPI's own
   *  `kpi_key`, which is globally unique — one definition, one owner process —
   *  so there is no second field holding the same string. */
  id: string;
  /** Where the reading belongs, already composed for display. */
  where: string;
  /** The instrument lines under the figure, in the platform's own terms. */
  lines: string[];
  /** The one true sentence for a reading that does not exist. Never a dash. */
  absence: string;
}

/** `primitive.kpi-dial@1`, off one entry of a district's plinth. */
interface DeskDial extends ReadingBase {
  kind: "dial";
  title: string;
  /** The KPI's own key, for looking its series up in the record. */
  measure: string;
  /** `null` where the plinth has no reading — either the snapshot job has never
   *  run for it (`measurable: false`) or the day it was last taken could not be
   *  computed (`value: null`). Renders as nothing. */
  current: { value: number } | null;
  /** Follows the numeral: `d`, `%`, and empty for a bare count or an amount. */
  unit: string;
}

/** `primitive.figure@1` — a district's envelope, which is the one aggregate the
 *  estate projection carries that is money-shaped. */
interface DeskFigure extends ReadingBase {
  kind: "figure";
  label: string;
  current: { figure: string } | null;
}

type DeskReading = DeskDial | DeskFigure;

/** A dial is titled; a figure is labelled. Both are the reading's name, and the
 *  echo, the heading and the button's accessible name all use this one. */
function nameOf(reading: DeskReading): string {
  return reading.kind === "dial" ? reading.title : reading.label;
}

/**
 * A number, grouped, with nothing else done to it.
 *
 * No symbol and no rounding to two places. The KPI registry declares
 * `unit: "currency"` and names no currency anywhere, and the envelope is stored
 * in USD columns the projection does not label — so a `₹` here would be a symbol
 * this client chose, which is the gap `StillSurface` records rather than fills.
 * The lines beneath the figure say so in words.
 */
function grouped(value: number): string {
  const digits = Math.abs(value) < 10 && !Number.isInteger(value) ? 1 : 0;
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(
    value,
  );
}

/** The suffix a unit gets, or nothing. Only the two the estate's own formatter
 *  recognises: an unrecognised unit prints no suffix rather than being spelled
 *  out beside a numeral it may not belong to. */
function suffixOf(unit: string): string {
  if (unit === "percent") return "%";
  if (unit === "days") return "d";
  return "";
}

/** One plinth KPI as a card. The two absences the projection keeps apart are
 *  kept apart here, and each gets its own sentence — "never taken" and "taken
 *  and not computable" are different facts about a young estate. */
function dialOf(kpi: PlinthKpi, where: string): DeskDial {
  const has = kpi.measurable && kpi.value !== null;
  return {
    kind: "dial",
    id: kpi.kpi_key,
    measure: kpi.kpi_key,
    title: kpi.display_name,
    where,
    current: has ? { value: kpi.value as number } : null,
    unit: suffixOf(kpi.unit),
    lines:
      kpi.unit === "currency"
        ? ["an amount · the platform stated no currency for it"]
        : [],
    absence: kpi.measurable
      ? "It was taken on the last snapshot and could not be computed that day."
      : "No snapshot has ever produced a value for it, and there is no backfill.",
  };
}

/** A district's envelope. `reserve_protected` is a boolean on the wire and not
 *  an amount, so the reserve is *stated* rather than drawn to scale — the same
 *  absence the district room's treasury gauge records. */
function envelopeOf(treasury: EstateTreasury, where: string): DeskFigure {
  return {
    kind: "figure",
    id: `envelope:${treasury.envelope_id}`,
    label: "Spent against the envelope",
    where,
    current: { figure: grouped(treasury.spent) },
    lines: [
      `of ${grouped(treasury.cap)} · the platform stated no currency for either`,
      treasury.reserve_protected
        ? "a reserve inside it is protected and never drains"
        : "no reserve is protected inside it",
    ],
    /* Unreachable while `current` is a computed figure, and written anyway: the
       type does not let a reading exist without a sentence for its own absence,
       which is what stops the next branch from falling back to a dash. */
    absence: "The estate reported no envelope for this district.",
  };
}

/** Everything the Desk can hold, in the projection's own order. */
function readingsOf(estate: EstateSnapshot): DeskReading[] {
  const out: DeskReading[] = [];
  for (const district of estate.districts) {
    const where = `${district.process_code} · ${district.name}`;
    for (const kpi of district.kpi.plinth) out.push(dialOf(kpi, where));
    if (district.treasury !== null) out.push(envelopeOf(district.treasury, where));
  }
  return out;
}

/* ---------------------------------------------------------------- the band */

interface VitalCell {
  label: string;
  figure: string;
}

/** The first KPI the estate can actually answer, in the projection's own order
 *  — the same stand-in `StillSurface` uses for the chooser D6 §2 names and the
 *  platform does not have. `null` where nothing is measurable, and then the
 *  cell is absent rather than filled. */
function leadMeasure(estate: EstateSnapshot): PlinthKpi | null {
  for (const district of estate.districts) {
    for (const kpi of district.kpi.plinth) {
      if (kpi.measurable && kpi.value !== null) return kpi;
    }
  }
  return null;
}

/**
 * The three readings the band carries.
 *
 * Each is a sum or a minimum over a collection that can be empty, and each is
 * written so that empty produces **no cell** rather than a number nobody
 * measured. `Math.min()` of nothing is `Infinity` and has shipped as a figure in
 * this app once already; the guard is the length check, not a `?? 0`.
 */
function vitalsOf(estate: EstateSnapshot): VitalCell[] {
  const cells: VitalCell[] = [];

  const lead = leadMeasure(estate);
  if (lead !== null && lead.value !== null) {
    cells.push({
      label: lead.display_name,
      figure: `${grouped(lead.value)}${suffixOf(lead.unit)}`,
    });
  }

  /* A counted zero prints — "nothing has come in this hour" is a real reading
     of a quiet estate, and the strip's job is to carry it.

     An estate with NO DISTRICTS is a different statement, and `reduce` over an
     empty list answers 0 for both. That is not a quiet hour, it is an estate
     nobody has built yet, and it is the ordinary state of a tenant's first
     fortnight. `StillSurface` reads the same snapshot and says "Your estate has
     not been built yet"; the band must not answer the same question with a
     number. Nothing counted is nothing shown (§7.1). */
  if (estate.districts.length > 0) {
    cells.push({
      label: "Signals an hour",
      figure: `${estate.districts.reduce((n, d) => n + d.traffic.in_1h, 0)}`,
    });
  }

  /* The soonest deadline the *server* computed. There is no "longest waited"
     figure on this wire and there cannot be one — `requested_at` is a naive
     column that `Date.parse` reads as local time, which is the whole reason
     `TraySurface` stopped printing "waited 34m". */
  const deadlines = estate.beacons
    .map((beacon) => beacon.sla_seconds_left)
    .filter((seconds): seconds is number => seconds !== null);
  if (deadlines.length > 0) {
    cells.push({ label: "Soonest decision", figure: remaining(Math.min(...deadlines)) });
  }

  return cells;
}

/** The server's own remainder, said in words — the Tray's rule, floored rather
 *  than rounded up, because "1h" with fifty-nine minutes gone is worse than
 *  "0h". */
function remaining(seconds: number): string {
  if (seconds <= 0) return "past";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

/** The estate's own wall-clock hour, read out of the projection's string rather
 *  than through `Date` — `local_time` already carries the deployment's estate
 *  timezone, and re-parsing it into the reader's would print an hour the phase
 *  beside it was not computed from. Unparseable → nothing. */
function estateHour(localTime: string): string | null {
  return /T(\d{2}):/.exec(localTime)?.[1] ?? null;
}

/* ------------------------------------------------------------------ pins -- */

/** The stored list, narrowed. The preference store's `value` is `unknown` by
 *  type and by contract, so anything that is not a list of strings is read as
 *  no pins — never as a crash, and never as a partially trusted list. */
function pinsIn(preferences: Record<string, PreferenceValue>): string[] {
  const value = preferences[LINE_PINS_KEY]?.value;
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === "string");
}

/* --------------------------------------------------------------- the desk -- */

export function PocketDesk({ onEcho }: { onEcho: (msg: string) => void }) {
  /* Live, not a one-shot read: the band's subject is *is anything wrong right
     now*, and a phone left open on this tab for an hour would otherwise be
     answering that question with an hour-old measurement. The frame subscribes
     to the same stream and `sharedStream` reference-counts it, so the two cost
     one connection. */
  const live = useLiveEstate();
  const stored = useResource(() => fetchPreferences(LINE_PINS_KEY));
  /* The record behind each dial. Optional by design: where it has not arrived,
     a card shows its reading and no trend, which is a card saying less rather
     than a card saying something untrue. */
  const record = useResource(() => fetchKpiHistory());

  /* The owner's list once they have moved it, and the store's until then. */
  const [moved, setMoved] = useState<string[] | null>(null);
  /* A write the store did not take. Held so the surface can say so, because the
     alternative is a card that moved on screen and nowhere else. */
  const [refused, setRefused] = useState<string | null>(null);

  if (live.phase === "loading" || stored.phase === "pending") return <DeskScaffold />;

  if (live.phase === "failed") {
    return (
      <section className="pd" aria-label="The pocket desk">
        <Failed what="the estate" reason={live.reason} onRetry={live.retry} />
      </section>
    );
  }

  const { estate, wire } = live;
  const readings = readingsOf(estate);
  const held = moved ?? (stored.phase === "ready" ? pinsIn(stored.value) : []);

  /* The stored order is the owner's order, so the pins drive the list and the
     catalogue is whatever is left in the estate's own order. A pinned id the
     estate no longer carries simply drops out — it is a reading that no longer
     exists, not an empty card. */
  const pinned = held
    .map((id) => readings.find((reading) => reading.id === id))
    .filter((reading): reading is DeskReading => reading !== undefined);
  const shelf = readings.filter((reading) => !held.includes(reading.id));

  const series = record.phase === "ready" ? record.value.series : [];
  const seriesFor = (measure: string): KpiSeries | undefined =>
    series.find((entry) => entry.key === measure);

  const hands = estate.beacons.length;
  const night = estate.estate.phase === "night";
  const hour = estateHour(estate.estate.local_time);

  const move = async (reading: DeskReading, onto: boolean): Promise<void> => {
    const next = onto
      ? [...held, reading.id]
      : held.filter((id) => id !== reading.id);
    setMoved(next);
    setRefused(null);
    try {
      await writePreference(LINE_PINS_KEY, next);
      /* Echoed only once the store took it (§8, and part C's rule about
         controls that look kept). */
      onEcho(
        `${onto ? "pinned" : "unpinned"} ${nameOf(reading)} ${
          onto ? "to" : "from"
        } the pocket desk`,
      );
    } catch {
      // Put it back. A reading that shows as pinned and is not pinned will be
      // gone the next time this phone is opened, with nothing having said so.
      setMoved(held);
      setRefused(
        `${nameOf(reading)} could not be ${
          onto ? "pinned" : "unpinned"
        } — the estate did not record it, so nothing has changed.`,
      );
    }
  };

  return (
    <section className="pd" aria-label="The pocket desk">
      {/* ============================================================ the vitals
          Never pinnable away, and never scrolled away either. */}
      <header className="pd-vitals m-glass" data-strong>
        <div className="pd-vitals-top">
          <span className="t-eyebrow">
            THE ESTATE · {night ? "NIGHT" : "DAY"}
            {hour !== null && ` · ${hour}:00`}
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
            this screen. Read through depth 0's own function rather than composed
            again here: D6 §1 requires the still line to be the same words
            wherever it appears, and one function is how that stays true. */}
        <h1 className="pd-still t-display">{stillLine(estate)}</h1>

        <dl className="pd-strip">
          {vitalsOf(estate).map((cell) => (
            <div className="pd-cell m-well" key={cell.label}>
              <dt className="t-eyebrow">{cell.label}</dt>
              <dd className="pd-cell-figure num">{cell.figure}</dd>
            </div>
          ))}
        </dl>

        <StaleLine wire={wire} />
      </header>

      {refused !== null && (
        <p className="pd-refused t-mono" role="status">
          <span className="m-lamp" data-negative />
          {refused}
        </p>
      )}

      {/* ============================================================ your pins */}
      {stored.phase === "failed" ? (
        /* L3 for one block, not the surface. The band above is real and the
           catalogue below is real; what could not be read is which of them you
           chose to keep, and saying "nothing pinned" would be a claim about
           the owner's own settings that this screen cannot make. */
        <Failed
          what="the readings you pinned"
          reason={stored.reason}
          onRetry={stored.retry}
          alone={false}
        />
      ) : readings.length === 0 ? (
        /* L2. The estate carries no measure and no envelope at all — a company
           whose blueprint has not been stood up yet. Distinct from "you have
           pinned nothing", which is a choice rather than an absence. */
        <Empty
          icon="trend"
          title="There is nothing to pin yet."
          body="The Desk holds readings — the measures your districts own and the envelopes they spend against. Your estate carries neither so far, so there is nothing here to keep in your pocket. The band above is the estate’s own state and it stands whatever happens next."
        />
      ) : pinned.length === 0 ? (
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
                series={reading.kind === "dial" ? seriesFor(reading.measure) : undefined}
                onUnpin={() => void move(reading, false)}
              />
            ))}
          </div>
        </section>
      )}

      {/* ======================================================== the catalogue
          The pinned readings are objects; what is not pinned is a list of data,
          so it lives in a well rather than on a dozen more plates. */}
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
                onPin={() => void move(reading, true)}
              />
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}

/**
 * The wire, when it is down (S3). Only when it is down: `connecting` is the
 * first half-second of every session and announcing it would train a person to
 * ignore the one line that matters. A band that says "nothing waiting on you"
 * while it has stopped listening is the single lie this surface must not tell.
 */
function StaleLine({ wire }: { wire: WireState }) {
  if (wire.status !== "stale") return null;
  return (
    <p className="pd-stale t-mono" role="status">
      <span className="m-lamp" data-negative />
      The estate has stopped sending updates, so this band may have moved on.
      {wire.retryInSeconds !== null && ` Trying again in ${wire.retryInSeconds}s.`}
    </p>
  );
}

function PinnedCard({
  reading,
  index,
  series,
  onUnpin,
}: {
  reading: DeskReading;
  index: number;
  series: KpiSeries | undefined;
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
        <DialBody dial={reading} series={series} />
      ) : (
        <FigureBody figure={reading} />
      )}
    </article>
  );
}

/**
 * `primitive.kpi-dial` at phone size: a figure, what it is in, and how far it
 * has come. No chart — a few days of series is not a line, and drawing one would
 * be the same lie as inventing the number. No meter either, and the surface's
 * header comment says why: nothing on the platform declares a target.
 */
function DialBody({ dial, series }: { dial: DeskDial; series: KpiSeries | undefined }) {
  const { current } = dial;

  /* Nothing in the series yet. One statement — the label, the reason, and where
     the record begins — and no trend beneath it, because two ways of saying the
     same absence would read as two faults. */
  if (current === null) {
    return <Absent why={dial.absence} from={startedOn(series)} />;
  }

  return (
    <>
      <p className="pd-read">
        <span className="pd-figure t-figure num">
          {grouped(current.value)}
          {/* The unit is set below the numeral's weight: it is what the number
              is in, not part of how big it is. */}
          {dial.unit !== "" && <span className="pd-unit">{dial.unit}</span>}
        </span>
      </p>

      {dial.lines.map((text) => (
        <Line text={text} key={text} />
      ))}

      <Trend series={series} current={current.value} unit={dial.unit} />
    </>
  );
}

/** `primitive.figure` — one aggregate and what it is of. No meter: an envelope's
 *  cap is a ceiling rather than a target, and it is said in words below. */
function FigureBody({ figure }: { figure: DeskFigure }) {
  if (figure.current === null) return <Absent why={figure.absence} from={null} />;

  return (
    <>
      <p className="pd-read">
        <span className="pd-figure t-figure num">{figure.current.figure}</span>
      </p>
      {figure.lines.map((text) => (
        <Line text={text} key={text} />
      ))}
    </>
  );
}

/** Where the record for this measure begins, as the history reports it. `null`
 *  when the record has not been read or has never held a measurable day — a
 *  young series that cannot say when it started says nothing about when. */
function startedOn(series: KpiSeries | undefined): string | null {
  if (series === undefined || series.first_measurable_on === null) return null;
  return `Measured from ${series.first_measurable_on} · nothing before it was backfilled`;
}

/**
 * The move since the series began.
 *
 * There is no week-on-week here and there will not be one until the record is
 * old enough: with no backfill, the only comparison a young series supports is
 * against its own first measured day. Where there is not even that, the slot
 * says so in a sentence — a slot left blank reads as a missing element, and a
 * stated absence reads as the truth.
 *
 * **Up and down, never better and worse.** `KpiDefinition` carries no direction,
 * so which way is good is a fact the platform does not hold; the lamp stays
 * unlit and the words stay neutral rather than this file deciding.
 */
function Trend({
  series,
  current,
  unit,
}: {
  series: KpiSeries | undefined;
  current: number;
  unit: string;
}) {
  // The record has not been read. Nothing true to say, so nothing is said.
  if (series === undefined) return null;

  const measured = series.points
    .filter((point) => point.measurable && point.value !== null)
    .sort((a, b) => a.captured_on.localeCompare(b.captured_on));
  const first = measured[0];

  if (first === undefined || measured.length < 2 || first.value === null) {
    return (
      <Line
        text={
          series.first_measurable_on === null
            ? "no earlier reading in the record"
            : `no earlier reading · the series starts ${series.first_measurable_on}`
        }
      />
    );
  }

  const moved = current - first.value;
  /* Unmoved is a reading too, and it is neither good nor bad — so it keeps the
     same unlit lamp as everything else here. */
  if (moved === 0) return <Line text={`unchanged since ${first.captured_on}`} />;

  return (
    <Line
      text={`${grouped(Math.abs(moved))}${unit} ${
        moved > 0 ? "higher" : "lower"
      } than ${first.captured_on} · from ${grouped(first.value)}${unit}`}
    />
  );
}

/**
 * One instrument line under a figure: a lamp, then a sentence.
 *
 * Every line beneath a reading is built this way so the sentences form one
 * column down the card. The lamp is that column's left edge — the same use the
 * frame's own notice makes of it — and it is unlit on every one of them, because
 * after the wiring there is no reading on this surface the platform grades as
 * good or bad.
 */
function Line({ text }: { text: string }) {
  return (
    <p className="pd-line">
      <span className="m-lamp" />
      <span className="t-mono">{text}</span>
    </p>
  );
}

/**
 * A reading that does not exist yet, drawn as a statement.
 *
 * The card keeps its shape — head, name, then this — so the young state is a
 * card that says something rather than a card missing its middle.
 */
function Absent({ why, from }: { why: string; from: string | null }) {
  return (
    <div className="pd-absent">
      <span className="t-eyebrow">NO READING YET</span>
      <p className="pd-absent-why t-mono">{why}</p>
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
  return reading.current === null
    ? null
    : `${grouped(reading.current.value)}${reading.unit}`;
}

/**
 * The pending state (D7 §3.1) — the Desk's own structure with the figures not
 * yet in it. No spinner: this is one of the seventeen.
 *
 * The band is drawn first because it is what the surface is for, and the bars go
 * *inside* the plates: `vh-skeleton`'s ground is a ~6/255 delta on the raw
 * canvas, so a bar over the page background draws nothing at all.
 */
function DeskScaffold() {
  return (
    <section className="pd" aria-label="The pocket desk">
      <Scaffold label="The pocket desk">
        <div className="pd-vitals m-glass" data-strong>
          <Bar width="xs" />
          <Bar width="lg" tall />
          <div className="pd-strip">
            {[0, 1, 2].map((i) => (
              <div className="pd-cell m-well" key={i}>
                <Bar width="sm" />
              </div>
            ))}
          </div>
        </div>
        <div className="pd-list pd-scaffold-list">
          {[0, 1].map((i) => (
            <div className="pd-card m-plate" key={i}>
              <Bar width="xs" />
              <Bar width="md" tall />
              <Lines n={2} />
            </div>
          ))}
        </div>
      </Scaffold>
    </section>
  );
}
