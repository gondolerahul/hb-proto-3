import { useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { Territory } from "../world/Territory";
import { DISTRICTS, DISTRICT_ROOMS, type Colleague } from "../fixtures/estate";
import "./district.css";

/**
 * District room · depth 2 · W+S (D6 §5).
 *
 * One Process, entered from its district on the Terrace. The room's structure is
 * the spec's: the place on the left (KPI, treasury, weather), the work on the
 * right (colleagues, live runs), traffic across the foot.
 *
 * The W half is the same `Territory` component the Terrace draws, in single-plot
 * mode — the district's own plinth and massing, no Sheel, no roads. Entering a
 * district does not change rendering technology, it changes distance; using the
 * one component is what makes that literally true (and it keeps RD-1/RD-2's
 * fixes: solid volumes, zero glyphs in the drawing).
 *
 * Two rules from the spec, held here:
 *   - **The protected reserve is the one gold thing on the treasury gauge.**
 *     Spend and cap are warm-white; the reserve seam never drains.
 *   - The whole surface renders from `estate/district/{code}` + the stream. A
 *     missing room fixture renders the honest-absence panel, not an invented one.
 */
export function DistrictSurface({
  code,
  onOpenHall,
  onEcho,
}: {
  code: string;
  onOpenHall: () => void;
  onEcho: (msg: string) => void;
}) {
  const district = DISTRICTS.find((d) => d.code === code);
  const room = DISTRICT_ROOMS[code];
  const [pausedIds, setPausedIds] = useState<Set<string>>(new Set());

  const seed = useMemo(
    () =>
      district
        ? [{ key: district.code, beacon: district.handsRaised > 0, traffic: 0 }]
        : [],
    [district],
  );

  if (!district) return null;

  return (
    <section className="di">
      {/* ------------------------------------------------------------ header */}
      <header className="di-head">
        <div>
          <span className="t-eyebrow">
            {district.code} · {district.process.toUpperCase()} ·{" "}
            {district.quarter.toUpperCase()}
          </span>
          <h1 className="di-title t-display">{district.name}</h1>
        </div>
        <button className="m-btn" data-rank="quiet" onClick={onOpenHall}>
          <Icon name="ledger" size={14} />
          Invoices hall
        </button>
      </header>

      <div className="di-body">
        {/* ==================================================== the place (W) */}
        <div className="di-place">
          <div className="di-diorama m-plate" data-sunken>
            <Territory
              districts={seed}
              gatehouses={[]}
              glasshouse={false}
              sheel={false}
              night
            />
          </div>

          {/* KPI ------------------------------------------------------------ */}
          {room && (
            <div className="di-kpi m-plate m-ticks">
              <span className="t-eyebrow">DAYS SALES OUTSTANDING</span>
              <div className="di-kpi-row">
                <span className="t-figure">{district.kpi.figure}</span>
                <span className="di-kpi-drift">
                  <span
                    className="m-lamp"
                    data-negative={district.kpi.drift === "behind" || undefined}
                    data-positive={district.kpi.drift === "ahead" || undefined}
                  />
                  <span className="t-mono">
                    {room.measure.value > room.measure.target
                      ? `${room.measure.value - room.measure.target}${room.measure.unit} over target · target ${room.measure.target}`
                      : `target ${room.measure.target} · on target`}
                  </span>
                </span>
              </div>
              <KpiMeter measure={room.measure} />
            </div>
          )}

          {/* Treasury ------------------------------------------------------- */}
          {room && (
            <div className="di-treasury m-plate">
              <div className="di-treasury-head">
                <span className="t-eyebrow">TREASURY · THIS MONTH</span>
                <span className="t-mono di-treasury-figures">
                  ₹{(room.treasury.spentINR / 1000).toFixed(0)}k of ₹
                  {(room.treasury.capINR / 1000).toFixed(0)}k
                </span>
              </div>
              <div className="di-gauge m-well" role="presentation">
                <span
                  className="di-gauge-spent"
                  style={{
                    width: `${(room.treasury.spentINR / room.treasury.capINR) * 100}%`,
                  }}
                />
                <span
                  className="di-gauge-reserve"
                  style={{
                    width: `${(room.treasury.reserveINR / room.treasury.capINR) * 100}%`,
                  }}
                  title="Protected reserve — never drains"
                />
              </div>
              <p className="t-mono di-treasury-note">
                <span className="di-reserve-key" aria-hidden="true" />
                ₹{(room.treasury.reserveINR / 1000).toFixed(0)}k protected reserve —
                the seam that never drains
              </p>
            </div>
          )}

          {/* Weather -------------------------------------------------------- */}
          {room && (
            <div className="di-weather">
              <div
                className="m-weather di-weather-mark"
                data-state={room.weather.state}
                aria-hidden="true"
              />
              <p className="di-weather-sentence">“{room.weather.sentence}”</p>
            </div>
          )}
        </div>

        {/* ===================================================== the work (S) */}
        <div className="di-work">
          <div className="di-colleagues m-plate">
            <span className="t-eyebrow">COLLEAGUES</span>
            <ul className="di-crew vh-stagger">
              {district.colleagues.map((c, i) => (
                <ColleagueRow
                  key={c.id}
                  colleague={c}
                  index={i}
                  onOpen={() => onEcho(`opened ${c.name}’s dossier`)}
                />
              ))}
            </ul>
          </div>

          {room && (
            <div className="di-runs m-plate">
              <span className="t-eyebrow">LIVE RUNS</span>
              <ul className="di-run-list m-well" data-deep>
                {room.runs.map((r) => {
                  const paused = pausedIds.has(r.id);
                  return (
                    <li className="di-run" key={r.id} data-paused={paused || undefined}>
                      <span
                        className="m-lamp"
                        data-lit={r.state === "running" && !paused ? true : undefined}
                      />
                      <button
                        className="di-run-open"
                        onClick={() => onEcho(`opened run ${r.id}`)}
                      >
                        <span className="di-run-doing">{r.doing}</span>
                        <span className="t-mono di-run-id">{r.id}</span>
                      </button>
                      <span className="t-mono di-run-elapsed">
                        {paused ? "paused" : r.state === "queued" ? "queued" : r.elapsed}
                      </span>
                      {r.state === "running" && (
                        <button
                          className="di-run-pause"
                          aria-label={paused ? `Resume ${r.doing}` : `Pause ${r.doing}`}
                          onClick={() => {
                            setPausedIds((prev) => {
                              const next = new Set(prev);
                              if (paused) next.delete(r.id);
                              else next.add(r.id);
                              return next;
                            });
                            onEcho(paused ? `resumed run ${r.id}` : `paused run ${r.id}`);
                          }}
                        >
                          <Icon name={paused ? "forward" : "hold"} size={13} />
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* ------------------------------------------------------------ traffic */}
      {room && (
        <footer className="di-traffic">
          {(
            [
              ["IN", `${room.traffic.inPerHour} signals/h`],
              ["OUT", `${room.traffic.outPerHour} signals/h`],
              ["PARKED", String(room.traffic.parked)],
            ] as const
          ).map(([label, value]) => (
            <button
              key={label}
              className="di-traffic-item"
              onClick={() => onEcho(`descended to the ${label.toLowerCase()} ledger`)}
              title="Opens in the Undercroft"
            >
              <span className="t-eyebrow">{label}</span>
              <span className="t-mono di-traffic-value">{value}</span>
            </button>
          ))}
        </footer>
      )}
    </section>
  );
}

/**
 * The track is the target; the overrun is terracotta past the tick. Scaled so
 * the worst value on screen still leaves 10% of headroom — a meter pinned to
 * its end reads as broken, not as bad.
 */
function KpiMeter({ measure }: { measure: { value: number; target: number } }) {
  const max = Math.max(measure.value, measure.target) * 1.1;
  const targetPct = (measure.target / max) * 100;
  const overPct = (Math.max(0, measure.value - measure.target) / max) * 100;
  return (
    <div className="di-meter" role="presentation">
      <span className="di-meter-fill" style={{ width: `${Math.min(measure.value, measure.target) / max * 100}%` }} />
      <span className="di-meter-over" style={{ left: `${targetPct}%`, width: `${overPct}%` }} />
      <span className="di-meter-tick" style={{ left: `${targetPct}%` }} />
    </div>
  );
}

const STANDING_LABEL: Record<Colleague["standing"], string> = {
  associate: "Associate",
  probationer: "Probationer",
  senior: "Senior",
};

function ColleagueRow({
  colleague: c,
  index,
  onOpen,
}: {
  colleague: Colleague;
  index: number;
  onOpen: () => void;
}) {
  return (
    <li style={{ ["--i" as string]: index }}>
      <button className="di-colleague" onClick={onOpen}>
        <span className="m-plinth di-colleague-plinth" aria-hidden="true">
          <span className="t-mono">{c.name.slice(0, 1)}</span>
        </span>
        <span className="di-colleague-who">
          <span className="di-colleague-name t-display">{c.name}</span>
          <span className="t-mono di-colleague-meta">
            {c.id} · {STANDING_LABEL[c.standing]}
          </span>
        </span>
        <span className="m-chip di-colleague-autonomy">{c.autonomy}</span>
        <span className="di-colleague-state">
          {c.handRaised ? (
            <>
              <span className="m-lamp" data-lit data-breathing />
              <span className="di-colleague-hand">hand raised</span>
            </>
          ) : c.doing ? (
            <>
              <span className="m-lamp" data-positive />
              <span className="t-mono">{c.doing}</span>
            </>
          ) : (
            <>
              <span className="m-lamp" />
              <span className="t-mono">idle</span>
            </>
          )}
        </span>
        <Icon name="chevron" size={13} className="di-colleague-caret" />
      </button>
    </li>
  );
}
