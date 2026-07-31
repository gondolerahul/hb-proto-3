import { useMemo, useState } from "react";
import { Territory, type GroundLabel } from "../world/Territory";
import type { PlotSeed } from "../world/layout";
import type { EstateSnapshot, WeatherState } from "../api/estate";
import { useLiveEstate } from "../estate/useLiveEstate";
import type { WireState } from "../estate/sharedStream";
import { Bar, Empty, Failed, Lines, Scaffold } from "../lifecycle";
import { formatMeasure, stillLine, worstWeather } from "./StillSurface";
import "./terrace.css";

/**
 * The Terrace · depth 1 · W (+S) (D6 §3) — on the live estate (R-4 part W · S).
 *
 * The estate seen whole, and the surface part S was built for: **beacons light
 * without a reload**. `useLiveEstate` gives one projection read plus the stream
 * reduced over it, so a raised hand becomes a gold shaft over its district in
 * the time the frame takes to arrive.
 *
 * **Owner review A2 reversed the label decision and was right to.** The labels
 * still lie on the floor as real SVG text, placed on clear ground outside the
 * slab, and the two defects RD-1 actually named (collision, size) are still
 * fixed structurally. Nothing about that changed here.
 *
 * What the wiring changed, and why.
 *
 * **1. Weather is the backend's sentence, never this file's.** The fixture
 * carried a five-state table with hand-written prose, three states of which
 * (`busy`, `fog`, `frost`) `estate.py` **cannot emit** — `fog` most importantly,
 * which D5 §2.1 derives from "below target for N snapshots" while
 * `KpiDefinition` declares no target to be below. A client branch for a state
 * the server can never reach is a working feature drawn over a known platform
 * gap (§7.4). The vocabulary is now the wire's four, and the sentence is the
 * one the projection wrote.
 *
 * **2. Weather is per district; the header states the estate's loudest.** It
 * ranks states the projection already decided rather than deciding one, and it
 * shares `stillLine` with depth 0 — D6 §1 requires the still line to be
 * "always the same words as depth 0", and one function is how that stays true.
 *
 * **3. The hands chip is a readout, not a control.** It used to `onEcho`
 * "opened the tray from the terrace" while opening nothing — an echo for an act
 * that did not happen, which is worse than no affordance. `TerraceSurface` has
 * no way to reach the Tray: its props are `onOpenDistrict` and `onEcho`, and
 * adding one belongs to `app/Prototype.tsx`, which this task does not own. So
 * it states the count, live, and the palette carries the navigation.
 *
 * **4. A dropped stream is marked (S3).** The count of raised hands and the
 * sentence about the estate are exactly the readings that look calm when they
 * are merely old, so the wire's own state sits beside them.
 */

/** The four states `estate.py` can emit, as words. `heat-shimmer` and
 *  `moonlit` are the two `material.css` has no texture for — see terrace.css. */
const WEATHER_WORD: Record<WeatherState, string> = {
  clear: "Clear",
  storm: "Storm",
  "heat-shimmer": "Heat shimmer",
  moonlit: "Moonlit",
};

/** Channel tokens as a person writes them. Presentation of the wire's own word,
 *  with a fall-through that capitalises whatever arrives rather than dropping a
 *  gatehouse this table has not met. */
const CHANNEL_WORD: Record<string, string> = {
  email: "Email",
  whatsapp: "WhatsApp",
  voice: "Voice",
  broadcast: "Broadcast",
};

function channelWord(channel: string): string {
  return CHANNEL_WORD[channel] ?? channel.charAt(0).toUpperCase() + channel.slice(1);
}

export function TerraceSurface({
  onOpenDistrict,
  onEcho,
}: {
  onOpenDistrict: (code: string) => void;
  onEcho: (msg: string) => void;
}) {
  const live = useLiveEstate();

  if (live.phase === "loading") {
    return (
      <section className="te" data-pending>
        <Scaffold label="The estate">
          {/* Plates first, bars inside them: `vh-skeleton` over the raw canvas
              is a ~6/255 delta and would draw nothing at all. */}
          <div className="te-scaffold">
            <div className="te-scaffold-head m-plate">
              <Bar width="sm" />
              <Bar width="lg" />
            </div>
            <div className="te-scaffold-stage m-plate">
              <Bar width="md" tall />
              <Lines n={2} />
            </div>
          </div>
        </Scaffold>
      </section>
    );
  }

  if (live.phase === "failed") {
    return (
      <section className="te" data-pending>
        <Failed what="the estate" reason={live.reason} onRetry={live.retry} />
      </section>
    );
  }

  if (live.estate.districts.length === 0) {
    return (
      <section className="te" data-pending>
        <Empty
          icon="district"
          alone
          title="There is no estate to draw yet."
          body="The Terrace shows quarters, the colleagues working in them and the roads that signals travel between them. None of that has been stood up here yet, so there is nothing to place on the ground — this is an empty estate, not a map that failed to arrive."
        />
      </section>
    );
  }

  return (
    <TerraceView
      estate={live.estate}
      wire={live.wire}
      onOpenDistrict={onOpenDistrict}
      onEcho={onEcho}
    />
  );
}

function TerraceView({
  estate,
  wire,
  onOpenDistrict,
  onEcho,
}: {
  estate: EstateSnapshot;
  wire: WireState;
  onOpenDistrict: (code: string) => void;
  onEcho: (msg: string) => void;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const night = estate.estate.phase === "night";

  const { districts, beacons, gatehouses } = estate;

  /** Which districts have a hand up. The beacon list is the estate's own
   *  authority on pending approvals, and it is the reading the stream keeps
   *  idempotently current across a reconnect (`beacon.raised` replays for every
   *  pending approval on connect). */
  const lit = useMemo(() => {
    const set = new Set<string>();
    for (const beacon of beacons) {
      if (beacon.district !== null) set.add(beacon.district);
    }
    return set;
  }, [beacons]);

  const seeds: PlotSeed[] = useMemo(
    () =>
      districts.map((district) => ({
        key: district.process_code,
        beacon: lit.has(district.process_code),
        traffic: district.traffic.in_1h,
      })),
    [districts, lit],
  );

  const gateKeys = useMemo(
    () => gatehouses.map((gatehouse) => gatehouse.gateway_code),
    [gatehouses],
  );

  const byCode = useMemo(
    () => new Map(districts.map((district) => [district.process_code, district])),
    [districts],
  );

  /**
   * Flat ground labels (owner review A2). Kept to a heading, one detail line and
   * the gold callout only where a hand is actually raised — a flat label is
   * legible in proportion to how little of it there is, and `LABEL_RUN` in
   * layout.ts frames the whole estate against a ~26-character budget, so a long
   * line here shrinks the territory to make room for itself.
   *
   * The detail line is the district's code plus its leading measurable KPI. A
   * district whose KPIs have never been snapshotted carries the code alone: a
   * plinth with no reading behind it prints no reading (§7.1).
   */
  const labels = useMemo<Record<string, GroundLabel>>(() => {
    const out: Record<string, GroundLabel> = {};
    for (const district of districts) {
      const measurable = district.kpi.plinth.find(
        (kpi) => kpi.measurable && kpi.value !== null,
      );
      const figure = measurable === undefined ? null : formatMeasure(measurable);
      out[district.process_code] = {
        heading: district.name,
        lines: [
          figure === null
            ? district.process_code
            : `${district.process_code} · ${figure}`,
        ],
        callout: lit.has(district.process_code) ? "needs you" : null,
      };
    }
    for (const gatehouse of gatehouses) {
      out[gatehouse.gateway_code] = {
        heading: channelWord(gatehouse.channel),
        lines: [gatehouse.gateway_code.toUpperCase()],
      };
    }
    out["glasshouse"] = {
      heading: "The Glasshouse",
      lines: ["simulation · not yet real"],
      drained: true,
    };
    return out;
  }, [districts, gatehouses, lit]);

  const weather = worstWeather(estate);
  const state: WeatherState = weather?.state ?? "clear";
  const waiting = beacons.length;

  const open = (code: string) => {
    onOpenDistrict(code);
    onEcho(`opened ${byCode.get(code)?.name ?? code}`);
  };

  return (
    <section className="te" data-night={night || undefined}>
      {/* ============================================================ the weather
          One sentence. Spec §4 wants weather readable identically day and night,
          and a sentence is the only form that is. */}
      <header className="te-weather">
        <div
          className="m-weather te-weather-mark"
          data-state={state}
          aria-hidden="true"
        />
        <div className="te-weather-text">
          <span className="t-eyebrow">
            THE ESTATE · {WEATHER_WORD[state].toUpperCase()} ·{" "}
            {night ? "NIGHT" : "DAY"}
          </span>
          <p className="te-weather-sentence">{stillLine(estate)}</p>
        </div>

        {/* One announcing region for the two things that change under the
            reader: what is waiting, and whether we are still watching. Both
            live here rather than in two regions — `BridgesSurface` settled that
            four announcing regions on one surface is noise. */}
        <div className="te-live" role="status">
          {waiting > 0 && (
            <p className="te-hands m-chip">
              {/* Sanctioned gold (§2.1): literally "this needs you". Never the
                  lamp alone — the words beside it are the correct read. */}
              <span className="m-lamp" data-lit data-breathing />
              {waiting} waiting on you
            </p>
          )}
          {wire.status === "stale" && (
            <p className="te-stale t-mono">
              <span className="m-lamp" data-negative aria-hidden="true" />
              The estate has stopped sending updates.
              {wire.retryInSeconds !== null &&
                ` Trying again in ${wire.retryInSeconds}s.`}
            </p>
          )}
        </div>
      </header>

      {/* ========================================================= the territory */}
      <div className="te-stage">
        <div className="te-plane">
          <Territory
            districts={seeds}
            gatehouses={gateKeys}
            labels={labels}
            navigable
            hoveredKey={hovered}
            onHover={setHovered}
            onOpen={(key) => {
              if (byCode.has(key)) open(key);
            }}
            night={night}
          />
        </div>
      </div>

      {/* ============================================================= the footer */}
      <footer className="te-foot">
        <p className="te-foot-still t-narrative t-muted">
          Drag to pan, scroll to zoom, double-click to reframe — or pick a
          quarter to walk into it.
        </p>
        <div className="te-foot-hops">
          {districts.map((district) => (
            <button
              key={district.process_code}
              className="m-chip"
              data-selected={hovered === district.process_code || undefined}
              onMouseEnter={() => setHovered(district.process_code)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => open(district.process_code)}
            >
              {lit.has(district.process_code) && (
                <span className="m-lamp" data-lit />
              )}
              {district.name}
            </button>
          ))}
        </div>
      </footer>
    </section>
  );
}
