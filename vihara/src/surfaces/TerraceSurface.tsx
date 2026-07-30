import { useMemo, useState } from "react";
import { Territory, type GroundLabel } from "../world/Territory";
import type { PlotSeed } from "../world/layout";
import { COMPANY, DISTRICTS, STILL } from "../fixtures/estate";
import "./terrace.css";

/**
 * The Terrace · depth 1 · W (+S) (D6 §3).
 *
 * The estate seen whole.
 *
 * **Owner review A2 reversed the label decision, and was right to.** Finding
 * RD-1 was that labels were skewed AND colliding AND too small to read — three
 * defects that arrived together, so "flat" got blamed for what collision and
 * size did. The inspiration set labels flat on the ground and reads beautifully.
 *
 * So the labels lie on the floor again, with the two real defects fixed
 * structurally rather than by taste:
 *
 *   - **They cannot collide with built form.** `buildTerritory` places each label
 *     on clear ground *outside* its slab, along the plot's own outward vector.
 *   - **They are set to be read.** Heading at display size, at most two detail
 *     lines, stroked against the floor so glyphs keep their edges under shear.
 *   - **They are still real text** — SVG `<text>`, so selectable and in the
 *     accessibility tree. Flatness was never what cost accessibility.
 *
 * The KPI's full sentence moved into the district room: a flat label is legible
 * in proportion to how little of it there is.
 *
 * **Weather** (spec §4) is one sentence, not an icon field. Five states, each a
 * texture + a sentence; the sentence is what a person acts on.
 */

const WEATHER = {
  clear: { label: "Clear", sentence: "Everything is moving at its usual pace." },
  busy: { label: "Busy", sentence: "Money quarter is carrying twice its normal load." },
  fog: { label: "Fog", sentence: "Two bridges have not reported in an hour." },
  storm: { label: "Storm", sentence: "Collections is nine days behind and falling." },
  frost: { label: "Frost", sentence: "The estate is quiet — credits are in read-only." },
} as const;

type WeatherState = keyof typeof WEATHER;

const GATEHOUSE_LABEL: Record<string, string> = {
  "kar-01": "Voice",
  "kar-02": "Email",
  "kar-03": "WhatsApp",
};

export function TerraceSurface({
  onOpenDistrict,
  onEcho,
}: {
  onOpenDistrict: (code: string) => void;
  onEcho: (msg: string) => void;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const night = COMPANY.localHour >= 19 || COMPANY.localHour < 6;
  const weather: WeatherState = "storm";

  const seeds: PlotSeed[] = useMemo(
    () =>
      DISTRICTS.map((d) => ({
        key: d.code,
        beacon: d.handsRaised > 0,
        traffic: d.signalsPerHour,
      })),
    [],
  );

  const gatehouses = useMemo(() => Object.keys(GATEHOUSE_LABEL), []);

  const byCode = useMemo(() => new Map(DISTRICTS.map((d) => [d.code, d])), []);

  /**
   * Flat ground labels (owner review A2). Every glyph on the territory is now
   * SVG text lying on the floor beside its structure — the register the
   * inspiration set uses, and still real selectable text.
   *
   * Kept to three short lines: a heading, one detail line, and the gold callout
   * only when a hand is actually raised. A flat label is legible in proportion
   * to how little of it there is, so the KPI's full sentence moves into the
   * district room rather than lying on the floor here.
   */
  const labels = useMemo<Record<string, GroundLabel>>(() => {
    /* Lines stay under ~26 characters. `LABEL_RUN` in layout.ts frames the
       estate against that budget, so a long line here does not just overflow —
       it shrinks the whole territory to make room for itself. */
    const out: Record<string, GroundLabel> = {};
    for (const d of DISTRICTS) {
      out[d.code] = {
        heading: d.name,
        lines: [
          `${d.code} · ${d.kpi.figure} ${d.kpi.drift === "flat" ? "steady" : d.kpi.drift}`,
        ],
        callout: d.handsRaised > 0 ? "needs you" : null,
      };
    }
    for (const [key, name] of Object.entries(GATEHOUSE_LABEL)) {
      out[key] = { heading: name, lines: [key.toUpperCase()] };
    }
    out["glasshouse"] = {
      heading: "The Glasshouse",
      lines: ["simulation · not yet real"],
      drained: true,
    };
    return out;
  }, []);

  const totalHands = DISTRICTS.reduce((n, d) => n + d.handsRaised, 0);

  return (
    <section className="te" data-night={night || undefined}>
      {/* ============================================================ the weather
          One sentence. Spec §4 wants weather readable identically day and night,
          and a sentence is the only form that is. */}
      <header className="te-weather">
        <div className="m-weather te-weather-mark" data-state={weather} aria-hidden="true" />
        <div className="te-weather-text">
          <span className="t-eyebrow">
            THE ESTATE · {WEATHER[weather].label.toUpperCase()} ·{" "}
            {night ? "NIGHT" : "DAY"}
          </span>
          <p className="te-weather-sentence">{WEATHER[weather].sentence}</p>
        </div>
        {totalHands > 0 && (
          <button
            className="te-hands m-chip"
            onClick={() => onEcho(`opened the tray from the terrace`)}
          >
            <span className="m-lamp" data-lit data-breathing />
            {totalHands} {totalHands === 1 ? "hand" : "hands"} raised
          </button>
        )}
      </header>

      {/* ========================================================= the territory */}
      <div className="te-stage">
        <div className="te-plane">
          <Territory
            districts={seeds}
            gatehouses={gatehouses}
            labels={labels}
            navigable
            hoveredKey={hovered}
            onHover={setHovered}
            onOpen={(key) => byCode.has(key) && onOpenDistrict(key)}
            night={night}
          />

        </div>
      </div>

      {/* ============================================================= the footer */}
      <footer className="te-foot">
        <p className="te-foot-still t-narrative">
          {STILL.headline} <span className="t-subtle">{"—"} </span>
          <span className="t-muted">
            drag to pan, scroll to zoom, double-click to reframe — or pick a quarter to walk into it.
          </span>
        </p>
        <div className="te-foot-hops">
          {DISTRICTS.map((d) => (
            <button
              key={d.code}
              className="m-chip"
              data-selected={hovered === d.code || undefined}
              onMouseEnter={() => setHovered(d.code)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onOpenDistrict(d.code)}
            >
              {d.handsRaised > 0 && <span className="m-lamp" data-lit />}
              {d.name}
            </button>
          ))}
        </div>
      </footer>
    </section>
  );
}
