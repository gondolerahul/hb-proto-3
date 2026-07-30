import { useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { Territory, buildTerritory } from "../world/Territory";
import type { PlotSeed } from "../world/layout";
import { COMPANY, DISTRICTS, STILL } from "../fixtures/estate";
import "./terrace.css";

/**
 * The Terrace · depth 1 · W (+S) (D6 §3).
 *
 * The estate seen whole. This is the surface finding **RD-1** damaged worst — its
 * labels were painted onto the ground plane and were unreadable — so the
 * architecture here is the fix:
 *
 *   - `Territory` draws **geometry only**. Not one glyph.
 *   - This component lays **DOM labels** over it, positioned by projecting each
 *     plot's anchor through the same isometric transform. Upright, selectable, in
 *     the accessibility tree, and legible at every zoom.
 *
 * The label layer is positioned in `viewBox` percentages rather than pixels, so
 * it tracks the SVG's `preserveAspectRatio` fit without a resize observer or a
 * per-frame projection. That is the whole trick, and it is why this needs no
 * WebGL to be correct.
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

  const { anchors, view } = useMemo(
    () => buildTerritory(seeds, gatehouses, true),
    [seeds, gatehouses],
  );

  /** viewBox units → percentage of the SVG's box, so labels track its fit. */
  const pct = (p: readonly [number, number]) => ({
    left: `${((p[0] - view.x) / view.w) * 100}%`,
    top: `${((p[1] - view.y) / view.h) * 100}%`,
  });

  const byCode = useMemo(() => new Map(DISTRICTS.map((d) => [d.code, d])), []);
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
            hoveredKey={hovered}
            onHover={setHovered}
            onOpen={(key) => byCode.has(key) && onOpenDistrict(key)}
            night={night}
          />

          {/* ------------------------------------------------- the DOM label layer
              Every glyph on this surface is here, in screen space. */}
          <div className="te-labels">
            {anchors.map((a) => {
              const d = byCode.get(a.key);
              const isGate = a.key in GATEHOUSE_LABEL;

              if (a.twin) {
                return (
                  <div
                    className="te-label te-label-twin"
                    key={a.key}
                    style={pct(a.at)}
                    data-side={a.side}
                  >
                    <span className="t-eyebrow">SIMULATION</span>
                    <span className="te-label-name t-display">The Glasshouse</span>
                    <span className="t-mono te-label-sub">nothing here can touch the real</span>
                  </div>
                );
              }

              if (isGate) {
                return (
                  <div
                    className="te-label te-label-gate"
                    key={a.key}
                    style={pct(a.at)}
                    data-side={a.side}
                  >
                    <span className="t-eyebrow">{a.key.toUpperCase()}</span>
                    <span className="te-label-gate-name">{GATEHOUSE_LABEL[a.key]}</span>
                  </div>
                );
              }

              if (!d) return null;

              return (
                <button
                  className="te-label te-label-district"
                  key={a.key}
                  style={pct(a.at)}
                  data-side={a.side}
                  data-hovered={hovered === a.key || undefined}
                  data-dimmed={(hovered && hovered !== a.key) || undefined}
                  onMouseEnter={() => setHovered(a.key)}
                  onMouseLeave={() => setHovered(null)}
                  onFocus={() => setHovered(a.key)}
                  onBlur={() => setHovered(null)}
                  onClick={() => onOpenDistrict(a.key)}
                >
                  <span className="t-eyebrow">
                    {d.code} · {d.quarter.toUpperCase()}
                  </span>
                  <span className="te-label-name t-display">{d.name}</span>

                  <span className="te-label-kpi">
                    <span className="te-label-figure">{d.kpi.figure}</span>
                    <span className="te-label-drift" data-drift={d.kpi.drift}>
                      <span
                        className="m-lamp"
                        data-positive={d.kpi.drift === "ahead" || undefined}
                        data-negative={d.kpi.drift === "behind" || undefined}
                      />
                      {d.kpi.label}
                    </span>
                  </span>

                  <span className="te-label-foot t-mono">
                    {d.colleagues.length}{" "}
                    {d.colleagues.length === 1 ? "colleague" : "colleagues"} ·{" "}
                    {d.signalsPerHour}/h
                    {d.handsRaised > 0 && (
                      <span className="te-label-hand">
                        <span className="m-lamp" data-lit data-breathing />
                        needs you
                      </span>
                    )}
                  </span>

                  <span className="te-label-enter" aria-hidden="true">
                    <Icon name="forward" size={12} />
                  </span>
                </button>
              );
            })}

            {/* The Sheel gets a mark, not a card — it is the centre, not a place
                you go. */}
            <div className="te-label te-label-sheel" style={pct([0, 0])}>
              <span className="t-eyebrow">THE PULSE</span>
              <span className="te-label-sheel-name">Sheel</span>
            </div>
          </div>
        </div>
      </div>

      {/* ============================================================= the footer */}
      <footer className="te-foot">
        <p className="te-foot-still t-narrative">
          {STILL.headline} <span className="t-subtle">{"—"} </span>
          <span className="t-muted">
            drag to look, scroll to zoom, or pick a quarter to walk into it.
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
