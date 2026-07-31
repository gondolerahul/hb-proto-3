import { Icon } from "../components/Icon";
import type { EstateSnapshot, EstateWeather, PlinthKpi, WeatherState } from "../api/estate";
import { fetchCompanyName } from "../api/identity";
import { useLiveEstate } from "../estate/useLiveEstate";
import type { WireState } from "../estate/sharedStream";
import { Bar, Empty, Failed, Scaffold, useResource } from "../lifecycle";
import "./still.css";

/**
 * Depth 0 · the Still Surface (D6 §2) — on the live estate (R-4 part W).
 *
 * Finding **RD-4**: the first build read "no chrome, because it *is* the chrome"
 * as "nothing on screen". The composition that answers it is unchanged — a
 * measured column at optical centre, a hairline, the hour as a horizon, one gold
 * line. What changed is where every word in it comes from.
 *
 * Four decisions a reader would otherwise have to reverse-engineer.
 *
 * **1. `useLiveEstate`, not a one-shot read.** Depth 0 is where a session sits
 * open for an hour, and the one sentence on it that matters is *is anything
 * waiting*. A `useResource` here would be honest only at the instant it loaded.
 * That also means this surface has a second reading to report — `wire` — and it
 * reports it: a dropped stream is **stale and marked**, never silently calm,
 * because a screen that says "Nothing needs you" while it has stopped listening
 * is the one lie this surface must not tell.
 *
 * **2. The scaffold draws a plate, then bars inside it.** `vh-skeleton`'s ground
 * is a 6/255 delta on the raw canvas — a bare bar over the background is
 * invisible, so the pending state would have *been* the blank screen RD-4
 * rejected. The plate is the structure; the bars are the words not yet in it.
 * It is drawn in the same render as mount, with no dynamic import and no
 * awaited state, which is what D7 §3.1's **120ms** first-scaffold budget for
 * this surface actually asks of the client.
 *
 * **3. The failure state offers a way onward, not only a retry.** Depth 0
 * renders no Shell (D6 §2), so there is no rail, no breadcrumb and no visible
 * way out of a failed read but the palette chord — which a first-time tenant
 * has no reason to know. The descend affordance therefore survives the failure.
 *
 * **4. Nothing is composed that the estate did not say.** The headline is the
 * backend's own weather sentence where there is one; the figure is a plinth KPI
 * with its own display name, or it is absent; the hands line is absent at zero.
 * The one place this surface *judges* is `stillLine`'s fall-through to "All is
 * well.", and that is a restatement of three booleans the projection ships, not
 * a fifth state invented here.
 *
 * The zero-gold-at-rest property (art bible §2.1) survives the wiring and is
 * still testable: with no beacons the only gold left is the brand mark.
 */

/**
 * Weather severity, in `estate.py`'s own precedence (storm > heat-shimmer >
 * moonlit > clear). This ranks states the projection has **already decided**;
 * it does not re-derive one. Re-deriving would be the mistake D8's read models
 * name — a panel that computes its own answer eventually disagrees with the
 * thing that actually decided it.
 */
const SEVERITY: Record<WeatherState, number> = {
  storm: 3,
  "heat-shimmer": 2,
  moonlit: 1,
  clear: 0,
};

/** The estate's loudest weather, or `null` when every district is clear —
 *  `clear` carries no sentence on purpose ("a calm district has nothing to
 *  show"), and manufacturing one here would be inventing calm. */
export function worstWeather(estate: EstateSnapshot): EstateWeather | null {
  let worst: EstateWeather | null = null;
  for (const district of estate.districts) {
    const { weather } = district;
    if (weather.state === "clear") continue;
    if (worst === null || SEVERITY[weather.state] > SEVERITY[worst.state]) {
      worst = weather;
    }
  }
  return worst;
}

/**
 * The depth-0 sentence. Exported because D6 §1 requires the shell's still line
 * to be *"always the same words as depth 0"* — one function is how that stays
 * true, and the Terrace already reads it.
 */
export function stillLine(estate: EstateSnapshot): string {
  const weather = worstWeather(estate);
  if (weather !== null && weather.sentence !== null) return weather.sentence;
  if (!estate.estate.pulse.healthy) return "The loop has missed a beat.";
  return "All is well.";
}

/**
 * A plinth KPI as a figure, or `null` where there is none to print.
 *
 * The two absences on the wire are kept apart by the projection and kept apart
 * here: `measurable === false` means the snapshot job has never run, `value ===
 * null` means the day was not measurable. Neither renders as `0` (§7.1).
 *
 * `currency` prints grouped and **unsigned** — the KPI registry declares
 * `unit: "currency"` and names no currency anywhere, so a `₹` here would be a
 * symbol this client chose. Recorded as a gap rather than guessed.
 */
export function formatMeasure(kpi: PlinthKpi): string | null {
  if (!kpi.measurable || kpi.value === null) return null;
  const value = kpi.value;
  const digits = Math.abs(value) < 10 && !Number.isInteger(value) ? 1 : 0;
  const figure = new Intl.NumberFormat(undefined, {
    maximumFractionDigits: digits,
  }).format(value);
  if (kpi.unit === "percent") return `${figure}%`;
  if (kpi.unit === "days") return `${figure}d`;
  return figure;
}

/** The first KPI the estate can actually answer, in the projection's own order.
 *  D6 §2 binds this slot to `kpi.business` *"chosen by LEARN's morning set"* —
 *  which does not exist, so the projection's order stands in for the chooser.
 *  What is NOT stood in for is the number: with nothing measurable the line is
 *  absent rather than filled. */
function leadMeasure(estate: EstateSnapshot): PlinthKpi | null {
  for (const district of estate.districts) {
    for (const kpi of district.kpi.plinth) {
      if (kpi.measurable && kpi.value !== null) return kpi;
    }
  }
  return null;
}

/**
 * The estate's own wall-clock hour, read out of the string rather than through
 * `Date`. `local_time` already carries the deployment's estate timezone
 * (`VIHARA_ESTATE_TIMEZONE`); re-parsing it into the *reader's* zone would
 * print a different hour than the one the projection computed `phase` from,
 * and the surface would say NIGHT beside 14:00. Unparseable → nothing.
 */
function estateHour(localTime: string): string | null {
  const match = /T(\d{2}):/.exec(localTime);
  return match?.[1] ?? null;
}

export function StillSurface({ onDescend }: { onDescend: () => void }) {
  const live = useLiveEstate();
  // Fail-soft by construction (`identity.ts` swallows and returns null), so
  // this read has no failure branch to draw — an unknown tenant name renders
  // as no tenant name, never as a placeholder.
  const company = useResource(fetchCompanyName);
  const name = company.phase === "ready" ? company.value : null;

  if (live.phase === "loading") {
    return (
      <section className="st">
        <div className="st-frame" aria-hidden="true">
          <div className="st-horizon" />
        </div>
        <Scaffold label="The estate">
          {/* The plate first, the bars inside it. A `vh-skeleton` bar on the
              raw canvas is a 6/255 delta and reads as nothing at all. */}
          <div className="st-scaffold m-plate">
            <Bar width="sm" />
            <Bar width="lg" tall />
            <Bar width="md" />
            <Bar width="sm" />
          </div>
        </Scaffold>
      </section>
    );
  }

  if (live.phase === "failed") {
    return (
      <section className="st">
        <div className="st-frame" aria-hidden="true">
          <div className="st-horizon" />
        </div>
        <div className="st-column">
          <Failed what="the estate" reason={live.reason} onRetry={live.retry} />
          {/* There is no Shell at depth 0, so this is the only visible way on.
              A failed front door that traps you is worse than a failed read. */}
          <Descend onDescend={onDescend} />
        </div>
      </section>
    );
  }

  const { estate, wire } = live;
  const night = estate.estate.phase === "night";
  const hour = estateHour(estate.estate.local_time);

  if (estate.districts.length === 0) {
    return (
      <section className="st" data-night={night || undefined}>
        <div className="st-frame" aria-hidden="true">
          <div className="st-horizon" />
        </div>
        <div className="st-column">
          <Eyebrow name={name} night={night} hour={hour} />
          <Empty
            icon="district"
            alone
            title="Your estate has not been built yet."
            body="There are no quarters, no districts and no colleagues here yet. Nothing is broken — there is simply nothing to show until the first process is stood up and someone is hired into it."
          />
          <Descend onDescend={onDescend} />
        </div>
      </section>
    );
  }

  const hands = estate.districts
    .flatMap((district) => district.colleagues)
    .filter((colleague) => colleague.hand_raised).length;
  /* Two readings of the same fact, and they can honestly disagree: `beacons` is
     every pending approval, `hands` is the colleagues above them. An approval
     whose run has no AGENT ancestor raises a beacon and nobody's hand, so the
     beacon list decides *whether* and the hands decide *who*. */
  const waiting = estate.beacons.length;
  const signals = estate.districts.reduce((n, d) => n + d.traffic.in_1h, 0);
  const measure = leadMeasure(estate);
  const figure = measure === null ? null : formatMeasure(measure);

  return (
    <section className="st" data-night={night || undefined}>
      {/* The hour, as the quietest possible frame. Not a clock — a horizon. */}
      <div className="st-frame" aria-hidden="true">
        <div className="st-horizon" />
      </div>

      <div className="st-column vh-stagger">
        <Eyebrow name={name} night={night} hour={hour} index={0} />

        <h1 className="st-line st-line-head" style={{ ["--i" as string]: 1 }}>
          {stillLine(estate)}
        </h1>

        {/* Absent, not zeroed, when nothing the estate measures has a reading
            yet — which is every tenant's first fortnight. */}
        {measure !== null && figure !== null && (
          <p className="st-line" style={{ ["--i" as string]: 2 }}>
            {measure.display_name} stands at{" "}
            <span className="num st-figure">{figure}</span>.
          </p>
        )}

        {waiting > 0 ? (
          <p className="st-line st-line-gold" style={{ ["--i" as string]: 3 }}>
            <span className="m-lamp st-hand" data-lit data-breathing />
            {hands > 0
              ? `${hands === 1 ? "One colleague is" : `${hands} colleagues are`} waiting for you.`
              : "Something is waiting for you in the tray."}
          </p>
        ) : (
          <p className="st-line t-muted" style={{ ["--i" as string]: 3 }}>
            Nothing needs you.
          </p>
        )}

        <hr className="m-rule-fade st-rule" style={{ ["--i" as string]: 4 }} />

        {/* The pulse. So the estate is visibly alive at rest — and visibly
            quiet, in words, when the hour brought nothing in. "0 signals an
            hour" is the reading part L flagged: true, and read as broken. */}
        <div className="st-pulse" style={{ ["--i" as string]: 5 }}>
          <span className="st-pulse-dot" aria-hidden="true" />
          {!estate.estate.pulse.healthy && (
            <span className="m-lamp" data-negative aria-hidden="true" />
          )}
          <span className="t-mono">
            {signals > 0
              ? `${signals} signals an hour`
              : "nothing has come in this hour"}{" "}
            · {estate.districts.length}{" "}
            {estate.districts.length === 1 ? "district" : "districts"} ·{" "}
            {estate.estate.pulse.healthy
              ? "the loop is answering"
              : "the loop has missed a beat"}
          </span>
        </div>

        <StaleLine wire={wire} index={6} />

        <Descend onDescend={onDescend} index={7} />
      </div>
    </section>
  );
}

function Eyebrow({
  name,
  night,
  hour,
  index,
}: {
  name: string | null;
  night: boolean;
  hour: string | null;
  index?: number;
}) {
  return (
    <div
      className="st-eyebrow"
      style={index === undefined ? undefined : { ["--i" as string]: index }}
    >
      <span className="sh-mark st-mark" aria-hidden="true">
        <span className="sh-mark-dot" />
      </span>
      {/* The tenant's own name, or nothing. A placeholder company here would be
          the first thing a person read and the first thing that was false. */}
      {name !== null && <span className="t-eyebrow">{name.toUpperCase()}</span>}
      {name !== null && <span className="st-eyebrow-sep" aria-hidden="true" />}
      <span className="t-eyebrow">
        {night ? "NIGHT" : "DAY"}
        {hour !== null && ` · ${hour}:00`}
      </span>
    </div>
  );
}

/**
 * The wire, when it is down (S3). Only when it is down: `connecting` is the
 * first half-second of every session and announcing it would train a person to
 * ignore the one line that matters. `role="status"` because this is the single
 * thing on the surface that can appear without the reader doing anything.
 */
function StaleLine({ wire, index }: { wire: WireState; index?: number }) {
  return (
    <div
      className="st-stale"
      role="status"
      style={index === undefined ? undefined : { ["--i" as string]: index }}
    >
      {wire.status === "stale" && (
        <p className="t-mono st-stale-text">
          <span className="m-lamp" data-negative aria-hidden="true" />
          The estate has stopped sending updates, so what you are reading may
          have moved on.
          {wire.retryInSeconds !== null &&
            ` Trying again in ${wire.retryInSeconds}s.`}
        </p>
      )}
    </div>
  );
}

/** The one affordance, and at depth 0 the only way onward that is on screen. */
function Descend({ onDescend, index }: { onDescend: () => void; index?: number }) {
  return (
    <button
      className="st-descend"
      onClick={onDescend}
      style={index === undefined ? undefined : { ["--i" as string]: index }}
    >
      <span className="t-eyebrow">GO DEEPER</span>
      <span className="st-descend-keys t-mono">
        <kbd>⌘</kbd>
        <kbd>↓</kbd>
      </span>
      <Icon name="down" size={13} className="st-descend-icon" />
    </button>
  );
}
