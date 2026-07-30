import { useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { Portrait } from "../components/Portrait";
import { Room, type RoomItem } from "../world/Room";
import { DISTRICTS, DISTRICT_ROOMS, type Colleague, type DistrictRoom } from "../fixtures/estate";
import "./district.css";

/**
 * District room · depth 2 · W+S (D6 §5).
 *
 * Rebuilt for owner review **B**: the room now has the Terrace's structure — a
 * place you look at and click into — instead of a column of panels beside a
 * small picture of one. Nothing was dropped; the same KPI, treasury, weather,
 * colleagues, live runs and traffic are all here. What changed is *when* you see
 * them: the room shows the place, and the detail opens on the structure you
 * click.
 *
 * Three decisions that carry it:
 *
 *  - **Colleagues are personified as architecture.** Each has a workplace on the
 *    district floor with its own built form, stable across sessions because the
 *    massing is derived from their position in the roster. That is the review's
 *    "structures rather than an icon with an alphabet": you learn where Meera
 *    works, and her building is recognisably hers. The generated portrait
 *    (art bible §7 direction A) appears when you open her.
 *  - **Fixtures are instruments, not cards.** The KPI is an obelisk — a reading
 *    standing up. The treasury is a low wide vault with the protected reserve as
 *    a gold seam across its face. Live runs are an almost-flat table: work laid
 *    out. Their form says what kind of thing they are before their label does.
 *  - **Nothing is selected on arrival.** The room opens as a room, and the panel
 *    is empty until you ask. A surface that pre-opens one panel is a surface that
 *    has decided for you which structure matters.
 */

const FIXTURE = { kpi: "fx-kpi", treasury: "fx-treasury", runs: "fx-runs" } as const;

export function DistrictSurface({
  code,
  onOpenHall,
  onOpenDossier,
  onEcho,
}: {
  code: string;
  onOpenHall: () => void;
  onOpenDossier?: (id: string) => void;
  onEcho: (msg: string) => void;
}) {
  const district = DISTRICTS.find((d) => d.code === code);
  const room = DISTRICT_ROOMS[code];
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [pausedIds, setPausedIds] = useState<Set<string>>(new Set());

  const items = useMemo<RoomItem[]>(() => {
    if (!district) return [];
    const out: RoomItem[] = [];

    if (room) {
      const over = room.measure.value - room.measure.target;
      out.push({
        key: FIXTURE.kpi,
        kind: "fixture",
        variant: 0,
        heading: "DSO",
        detail: `${district.kpi.figure} · target ${room.measure.target}`,
        callout: null,
        lit: false,
      });
      out.push({
        key: FIXTURE.treasury,
        kind: "fixture",
        variant: 1,
        heading: "Treasury",
        detail: `₹${(room.treasury.spentINR / 1000).toFixed(0)}k of ₹${(room.treasury.capINR / 1000).toFixed(0)}k`,
        seam: { at: room.treasury.reserveINR, of: room.treasury.capINR },
        lit: false,
      });
      out.push({
        key: FIXTURE.runs,
        kind: "fixture",
        variant: 2,
        heading: "Live runs",
        detail: `${room.runs.filter((r) => r.state === "running").length} running`,
        lit: room.runs.some((r) => r.state === "running"),
      });
      // `over` exists to be read by the KPI panel; naming it here keeps the
      // fixture list honest about what the obelisk is measuring.
      void over;
    }

    for (const [i, c] of district.colleagues.entries()) {
      out.push({
        key: c.id,
        kind: "workplace",
        variant: i,
        heading: c.name,
        detail: `${c.id} · ${c.autonomy}`,
        callout: c.handRaised ? "needs you" : null,
        lit: Boolean(c.doing) && !c.handRaised,
        beacon: c.handRaised,
      });
    }
    return out;
  }, [district, room]);

  if (!district) return null;

  const colleague = district.colleagues.find((c) => c.id === selected) ?? null;

  return (
    <section className="di">
      {/* ------------------------------------------------------------ header */}
      <header className="di-head">
        <div className="di-head-lead">
          <span className="t-eyebrow">
            {district.code} · {district.process.toUpperCase()} · {district.quarter.toUpperCase()}
          </span>
          <h1 className="di-title t-display">{district.name}</h1>
        </div>

        {room && (
          <div className="di-head-weather">
            <div className="m-weather di-weather-mark" data-state={room.weather.state} aria-hidden="true" />
            <p className="di-weather-sentence">“{room.weather.sentence}”</p>
          </div>
        )}

        <button className="m-btn di-head-hall" data-rank="quiet" onClick={onOpenHall}>
          <Icon name="ledger" size={14} />
          Invoices hall
        </button>
      </header>

      {/* ============================================================= the room */}
      <div className="di-body">
        <div className="di-stage">
          <Room
            items={items}
            selectedKey={selected}
            hoveredKey={hovered}
            onHover={setHovered}
            onSelect={(key) => setSelected((s) => (s === key ? null : key))}
          />
        </div>

        {/* ------------------------------------------------------ the reveal
            Everything the old surface showed at once, shown when asked for. */}
        <aside className="di-reveal" aria-live="polite">
          {selected === null && <RoomLegend district={district} room={room} />}

          {colleague && (
            <ColleaguePanel
              colleague={colleague}
              onClose={() => setSelected(null)}
              onOpenDossier={onOpenDossier}
              onEcho={onEcho}
            />
          )}

          {selected === FIXTURE.kpi && room && (
            <KpiPanel district={district} room={room} onClose={() => setSelected(null)} />
          )}

          {selected === FIXTURE.treasury && room && (
            <TreasuryPanel room={room} onClose={() => setSelected(null)} />
          )}

          {selected === FIXTURE.runs && room && (
            <RunsPanel
              room={room}
              pausedIds={pausedIds}
              onToggle={(id) => {
                setPausedIds((prev) => {
                  const next = new Set(prev);
                  const wasPaused = next.has(id);
                  if (wasPaused) next.delete(id);
                  else next.add(id);
                  onEcho(wasPaused ? `resumed run ${id}` : `paused run ${id}`);
                  return next;
                });
              }}
              onOpen={(id) => onEcho(`opened run ${id}`)}
              onClose={() => setSelected(null)}
            />
          )}
        </aside>
      </div>

      {/* ----------------------------------------------------------- traffic */}
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
          <p className="di-traffic-hint t-mono">click a structure to open it</p>
        </footer>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ panels -- */

function PanelHead({
  eyebrow,
  title,
  onClose,
}: {
  eyebrow: string;
  title: string;
  onClose: () => void;
}) {
  return (
    <header className="di-panel-head">
      <div>
        <span className="t-eyebrow">{eyebrow}</span>
        <h2 className="di-panel-title t-display">{title}</h2>
      </div>
      <button className="di-panel-close" onClick={onClose} aria-label="Close the panel">
        <Icon name="close" size={14} />
      </button>
    </header>
  );
}

/** With nothing selected the panel explains the room rather than sitting empty. */
function RoomLegend({
  district,
  room,
}: {
  district: (typeof DISTRICTS)[number];
  room: DistrictRoom | undefined;
}) {
  return (
    <div className="di-legend vh-enter-fade">
      <span className="t-eyebrow">THE ROOM</span>
      <p className="t-narrative di-legend-body">
        {district.colleagues.length} colleagues work here, and three instruments
        report on the place. Click any structure to open it.
      </p>
      <hr className="m-rule-fade" />
      <dl className="di-legend-list">
        {[
          ["Back row", "the readings — DSO, the treasury, live runs"],
          ["Front row", "the colleagues, each at their own workplace"],
          ["A gold shaft", "a colleague with a hand raised"],
          ["A gold seam", "the protected reserve, which never drains"],
        ].map(([k, v]) => (
          <div className="di-legend-row" key={k}>
            <dt className="t-eyebrow">{k}</dt>
            <dd className="di-legend-val">{v}</dd>
          </div>
        ))}
      </dl>
      {room && (
        <p className="di-legend-foot t-mono">
          {room.runs.length} runs on the table · {district.handsRaised} hand
          {district.handsRaised === 1 ? "" : "s"} raised
        </p>
      )}
    </div>
  );
}

const STANDING_LABEL: Record<Colleague["standing"], string> = {
  associate: "Associate",
  probationer: "Probationer",
  senior: "Senior",
};

function ColleaguePanel({
  colleague: c,
  onClose,
  onOpenDossier,
  onEcho,
}: {
  colleague: Colleague;
  onClose: () => void;
  onOpenDossier?: (id: string) => void;
  onEcho: (msg: string) => void;
}) {
  return (
    <div className="di-panel vh-enter">
      <PanelHead eyebrow={`COLLEAGUE · ${c.role.toUpperCase()}`} title={c.name} onClose={onClose} />

      <div className="di-who">
        <div className="m-portrait-well di-who-portrait">
          <Portrait id={c.id} size={72} />
        </div>
        <dl className="di-who-facts">
          {[
            ["Id", c.id],
            ["Standing", STANDING_LABEL[c.standing]],
            ["Autonomy", c.autonomy],
          ].map(([k, v]) => (
            <div className="di-fact" key={k}>
              <dt className="t-eyebrow">{k}</dt>
              <dd className="t-mono di-fact-val">{v}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="m-well di-state">
        {c.handRaised ? (
          <p className="di-state-line">
            <span className="m-lamp" data-lit data-breathing />
            <span className="di-state-gold">She is waiting for you.</span> Her card
            is in the tray.
          </p>
        ) : c.doing ? (
          <p className="di-state-line">
            <span className="m-lamp" data-positive />
            Right now: {c.doing}.
          </p>
        ) : (
          <p className="di-state-line">
            <span className="m-lamp" />
            Idle — nothing has come in for her.
          </p>
        )}
      </div>

      <div className="di-panel-acts">
        <button className="m-btn" onClick={() => onOpenDossier?.(c.id)}>
          <Icon name="colleague" size={13} />
          Open her dossier
        </button>
        <button
          className="m-btn"
          data-rank="quiet"
          onClick={() => onEcho(`told ${c.name} to hold`)}
        >
          <Icon name="hold" size={13} />
          Hold her work
        </button>
      </div>
    </div>
  );
}

function KpiPanel({
  district,
  room,
  onClose,
}: {
  district: (typeof DISTRICTS)[number];
  room: DistrictRoom;
  onClose: () => void;
}) {
  const { value, target, unit } = room.measure;
  const max = Math.max(value, target) * 1.1;
  const targetPct = (target / max) * 100;
  const overPct = (Math.max(0, value - target) / max) * 100;

  return (
    <div className="di-panel vh-enter">
      <PanelHead eyebrow="THE READING" title="Days sales outstanding" onClose={onClose} />

      <div className="di-kpi-row">
        <span className="t-figure">{district.kpi.figure}</span>
        <span className="di-kpi-drift">
          <span
            className="m-lamp"
            data-negative={district.kpi.drift === "behind" || undefined}
            data-positive={district.kpi.drift === "ahead" || undefined}
          />
          <span className="t-mono">
            {value > target
              ? `${value - target}${unit} over target · target ${target}`
              : `target ${target} · on target`}
          </span>
        </span>
      </div>

      {/* The track is the target; the overrun is terracotta past the tick. Scaled
          so the worst value still leaves headroom — a meter pinned to its end
          reads as broken rather than as bad. */}
      <div className="di-meter" role="presentation">
        <span
          className="di-meter-fill"
          style={{ width: `${(Math.min(value, target) / max) * 100}%` }}
        />
        <span className="di-meter-over" style={{ left: `${targetPct}%`, width: `${overPct}%` }} />
        <span className="di-meter-tick" style={{ left: `${targetPct}%` }} />
      </div>

      <p className="t-narrative di-panel-body">{room.weather.sentence}</p>
    </div>
  );
}

function TreasuryPanel({ room, onClose }: { room: DistrictRoom; onClose: () => void }) {
  const { spentINR, capINR, reserveINR } = room.treasury;
  return (
    <div className="di-panel vh-enter">
      <PanelHead eyebrow="THE VAULT" title="Treasury · this month" onClose={onClose} />

      <div className="di-gauge m-well" role="presentation">
        <span className="di-gauge-spent" style={{ width: `${(spentINR / capINR) * 100}%` }} />
        <span
          className="di-gauge-reserve"
          style={{ width: `${(reserveINR / capINR) * 100}%` }}
          title="Protected reserve — never drains"
        />
      </div>

      <dl className="di-who-facts di-treasury-facts">
        {[
          ["Spent", `₹${spentINR.toLocaleString("en-IN")}`],
          ["Envelope", `₹${capINR.toLocaleString("en-IN")}`],
          ["Reserve", `₹${reserveINR.toLocaleString("en-IN")}`],
        ].map(([k, v]) => (
          <div className="di-fact" key={k}>
            <dt className="t-eyebrow">{k}</dt>
            <dd className="t-mono di-fact-val">{v}</dd>
          </div>
        ))}
      </dl>

      <p className="di-panel-note t-mono">
        <span className="di-reserve-key" aria-hidden="true" />
        The reserve is the seam that never drains. Work stops before it is spent,
        so a runaway process cannot empty the envelope.
      </p>
    </div>
  );
}

function RunsPanel({
  room,
  pausedIds,
  onToggle,
  onOpen,
  onClose,
}: {
  room: DistrictRoom;
  pausedIds: Set<string>;
  onToggle: (id: string) => void;
  onOpen: (id: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="di-panel vh-enter">
      <PanelHead eyebrow="THE TABLE" title="Live runs" onClose={onClose} />
      <ul className="di-run-list m-well" data-deep>
        {room.runs.map((r) => {
          const paused = pausedIds.has(r.id);
          return (
            <li className="di-run" key={r.id} data-paused={paused || undefined}>
              <span
                className="m-lamp"
                data-lit={r.state === "running" && !paused ? true : undefined}
              />
              <button className="di-run-open" onClick={() => onOpen(r.id)}>
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
                  onClick={() => onToggle(r.id)}
                >
                  <Icon name={paused ? "forward" : "hold"} size={13} />
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
