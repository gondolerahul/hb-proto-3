import { useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { Portrait } from "../components/Portrait";
import { Room, type RoomItem } from "../world/Room";
import { artKeyFor, fetchExecutions, type RunSummary } from "../api/entities";
import type {
  EstateColleague,
  EstateDistrict,
  EstateSnapshot,
  PlinthKpi,
  WeatherState,
} from "../api/estate";
import { useLiveEstate } from "../estate/useLiveEstate";
import type { WireState } from "../estate/sharedStream";
import { Bar, Empty, Failed, Lines, Scaffold, useResource } from "../lifecycle";
import { formatMeasure } from "./StillSurface";
import "./district.css";

/**
 * District room · depth 2 · W+S (D6 §5) — on the live estate (R-4 part W · S).
 *
 * The room's *shape* is owner review B's and is untouched: a place you look at
 * and click into, colleagues personified as built form, fixtures as
 * instruments, nothing selected on arrival. What changed is where every number
 * in it comes from, and four of them turned out not to exist.
 *
 * **1. It reads the live estate, not `fetchDistrict`.** Both doors serve the
 * same projection, but this is the surface `stream.py` actually emits for:
 * `traffic`, `weather.changed`, `envelope.burn` and `run.state` are all
 * per-district frames, and `live.ts` reduces every one of them into
 * `EstateSnapshot.districts`. A one-shot `GET …/district/{code}` would leave
 * this room holding whatever the numbers were when you walked in. `fetchDistrict`
 * stays wrapped for a caller that wants one district and its own `as_of`.
 *
 * **2. The shape reconcile went the wire's way** (`api/estate.ts` decided it,
 * this file follows it): `in_1h`/`out_1h`, and a weather vocabulary closed at
 * **four**. The fixture's `fog` is a named absence — D5 §2.1 derives it from
 * "below target for N snapshots" and no KPI declares a target — so there is no
 * `fog` branch here to be dead code. Two of the four states have no texture in
 * `material.css`; they get one on this file's own class, exactly as
 * `terrace.css` does, rather than by restyling `m-weather`.
 *
 * **3. A code that names no district is a designed answer.** `Prototype` falls
 * back to `"P08"` when the URL carries no subject, and `DISTRICT_ROOMS` had
 * exactly one key — so every district but Collections used to render a header
 * with an empty room under it. A code the estate does not know now says so, in
 * prose, and names the codes it does know.
 *
 * ## Three instruments lost a scale, and none of them kept a drawn one
 *
 * This is the §7.1/§7.4 half of the wiring, and it is most of the diff.
 *
 * - **The KPI obelisk had a target tick. Nothing on the platform declares a
 *   target.** `PlinthKpi` is `{value, measurable, unit}` and `KpiDefinition`
 *   carries a baseline and no target — the same hole that keeps `fog` off the
 *   weather. So the meter is gone rather than drawn against a number this
 *   client chose, and the panel lists every reading on the plinth with the two
 *   absences kept apart: never measured (no snapshot) and not measurable today.
 * - **The treasury's protected reserve is a boolean.** The envelope row holds
 *   `reserved_usd`; the projection reports only whether it is above zero (gap
 *   R-4-P-1). A gold seam is a *width*, and there is no width — so the fact is
 *   stated in words and the gauge draws spend against cap only.
 * - **A run does not say what it is doing.** `RunSummary` is status, timings and
 *   an error; the dossier read model names this same hole as its `doing`
 *   absence. So the table lists runs by their colleague and their id, and says
 *   once that no run records a sentence.
 * - **Pause and resume were echoes over nothing.** No endpoint pauses a run —
 *   `POST /ai/executions/{id}/cancel` ends one outright, which is a different
 *   act — so the controls are gone rather than left doing nothing to the estate
 *   while telling the owner they did something.
 *
 * The traffic strip became a readout for the same reason the Terrace's hands
 * chip did: it echoed "descended to the ledger" and descended nowhere, and this
 * surface has no way to reach the Undercroft.
 *
 * **No certified act lives here.** "Hold her work" had no endpoint behind it and
 * is not in `CERTIFIED_ACTS`; the room's only real navigation is the register
 * and the dossier, and both are plain.
 */

const FIXTURE = { kpi: "fx-kpi", treasury: "fx-treasury", runs: "fx-runs" } as const;

/** The four states `estate.py` can emit, as words. Shared vocabulary with the
 *  Terrace; the sentence, when there is one, is always the projection's. */
const WEATHER_WORD: Record<WeatherState, string> = {
  clear: "Clear",
  storm: "Storm",
  "heat-shimmer": "Heat shimmer",
  moonlit: "Moonlit",
};

/** `ACTIVE_RUN_STATUSES` as the estate composes it — the same set the dossier's
 *  `running_runs` counts, so two surfaces cannot disagree about what "running"
 *  means. Anything else is printed as the wire's own word. */
const ACTIVE = new Set(["RUNNING", "PENDING", "PAUSED", "AWAITING_APPROVAL"]);

const FAILED = new Set(["FAILED", "CANCELLED", "TIMEOUT", "REFUSED"]);

/** Three-digit grouping, locale-free — the same reasoning `HallSurface` gives:
 *  `toLocaleString` reformats money with whatever ICU data the machine carries,
 *  so one envelope would read differently on two browsers. */
function grouped(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  const text = String(rounded);
  const negative = text.startsWith("-");
  const bare = negative ? text.slice(1) : text;
  const [whole, ...rest] = bare.split(".");
  if (whole === undefined || !/^\d+$/.test(whole)) return text;
  let out = "";
  for (let i = 0; i < whole.length; i += 1) {
    if (i > 0 && (whole.length - i) % 3 === 0) out += ",";
    out += whole[i]!;
  }
  return `${negative ? "-" : ""}${out}${rest.length > 0 ? `.${rest.join(".")}` : ""}`;
}

/** The server's own timestamp, to the second. Never a relative age: these
 *  columns are naive and carry no offset, so "4 h ago" is wrong by the reader's
 *  timezone (the precedent is `hall.css`'s FILED column). */
function stamp(iso: string): string {
  return iso.replace("T", " ").slice(0, 19);
}

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
  const live = useLiveEstate();

  if (live.phase === "loading") return <DistrictScaffold />;

  if (live.phase === "failed") {
    return (
      <section className="di di-flat">
        <Failed what="this district" reason={live.reason} onRetry={live.retry} />
      </section>
    );
  }

  const district = live.estate.districts.find((d) => d.process_code === code);

  if (district === undefined) {
    return (
      <section className="di di-flat">
        <UnknownDistrict code={code} estate={live.estate} />
      </section>
    );
  }

  return (
    <DistrictRoom
      key={district.process_code}
      district={district}
      wire={live.wire}
      onOpenHall={onOpenHall}
      onOpenDossier={onOpenDossier}
      onEcho={onEcho}
    />
  );
}

/**
 * A URL naming a district this company does not have.
 *
 * Two different facts, and they get two different sentences: an estate with no
 * districts at all has not been stood up, and an estate with districts that
 * does not have *this* one is a bad link. Collapsing them would tell a new
 * company its estate is broken and an old one that it is empty.
 */
function UnknownDistrict({ code, estate }: { code: string; estate: EstateSnapshot }) {
  if (estate.districts.length === 0) {
    return (
      <Empty
        alone
        icon="district"
        title="No district has been stood up yet."
        body="A district is one business process with a wall around it — the colleagues who work in it, the readings that report on it and the envelope it spends from. None exists here yet, so there is no room to walk into."
      />
    );
  }
  return (
    <Empty
      alone
      icon="district"
      title={`This estate has no district called ${code}.`}
      body="The address named a process code, and the estate does not answer to it. Nothing is broken and nothing is hidden — either the link is old, or the district belongs to a different company."
      note={`the estate names ${estate.districts.map((d) => d.process_code).join(", ")}`}
    />
  );
}

function DistrictRoom({
  district,
  wire,
  onOpenHall,
  onOpenDossier,
  onEcho,
}: {
  district: EstateDistrict;
  wire: WireState;
  onOpenHall: () => void;
  onOpenDossier?: (id: string) => void;
  onEcho: (msg: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  const measurable = district.kpi.plinth.filter(
    (kpi) => kpi.measurable && kpi.value !== null,
  );
  const running = district.colleagues.filter((c) => c.state === "running").length;
  const handsRaised = district.colleagues.filter((c) => c.hand_raised).length;

  const items = useMemo<RoomItem[]>(() => {
    const out: RoomItem[] = [];
    const lead = district.kpi.plinth.find((kpi) => kpi.measurable && kpi.value !== null);

    if (district.kpi.plinth.length > 0) {
      out.push({
        key: FIXTURE.kpi,
        kind: "fixture",
        variant: 0,
        heading: "Readings",
        /* A plinth with nothing measurable prints no figure — never a zero and
           never a dash. The obelisk still stands, because the KPI is declared;
           it just has no number on it yet. */
        detail: (() => {
          const reading = lead === undefined ? null : formatMeasure(lead);
          if (lead === undefined || reading === null) {
            return `${district.kpi.plinth.length} declared`;
          }
          return `${lead.display_name} · ${reading}`;
        })(),
        callout: null,
        lit: false,
      });
    }

    if (district.treasury !== null) {
      out.push({
        key: FIXTURE.treasury,
        kind: "fixture",
        variant: 1,
        heading: "Treasury",
        detail: `${grouped(district.treasury.spent)} of ${grouped(district.treasury.cap)}`,
        /* No seam. `reserve_protected` is a boolean — there is no width to draw
           it to scale, and a gold band of a width nobody stated would be a
           measurement this client invented (gap R-4-P-1). */
        lit: false,
      });
    }

    if (district.colleagues.length > 0) {
      out.push({
        key: FIXTURE.runs,
        kind: "fixture",
        variant: 2,
        heading: "Live runs",
        detail: `${running} running`,
        lit: running > 0,
      });
    }

    for (const [i, colleague] of district.colleagues.entries()) {
      out.push({
        key: colleague.entity_id,
        kind: "workplace",
        variant: i,
        heading: colleague.name,
        detail: colleague.autonomy,
        callout: colleague.hand_raised ? "needs you" : null,
        lit: colleague.state === "running" && !colleague.hand_raised,
        beacon: colleague.hand_raised,
      });
    }
    return out;
  }, [district, running]);

  const colleague =
    district.colleagues.find((c) => c.entity_id === selected) ?? null;

  /* Opening a structure is the act this room takes, so it is the act that
     echoes (§8) — and the echo is computed here rather than inside the state
     updater, which StrictMode runs twice. Closing is not an act. */
  const open = (key: string) => {
    if (selected === key) {
      setSelected(null);
      return;
    }
    setSelected(key);
    const who = district.colleagues.find((c) => c.entity_id === key);
    if (who !== undefined) onEcho(`opened ${who.name}’s workplace`);
  };

  return (
    <section className="di">
      {/* ------------------------------------------------------------ header */}
      <header className="di-head">
        <div className="di-head-lead">
          <span className="t-eyebrow">
            {district.process_code} · {district.quarter.toUpperCase()}
          </span>
          <h1 className="di-title t-display">{district.name}</h1>
        </div>

        <div className="di-head-weather">
          <div
            className="m-weather di-weather-mark"
            data-state={district.weather.state}
            aria-hidden="true"
          />
          {/* The projection's own sentence, or its own word. Never one composed
              here: a district's weather is a read, not a description. */}
          <p className="di-weather-sentence">
            {district.weather.sentence !== null
              ? `“${district.weather.sentence}”`
              : WEATHER_WORD[district.weather.state]}
          </p>
        </div>

        <button className="m-btn di-head-hall" data-rank="quiet" onClick={onOpenHall}>
          <Icon name="ledger" size={14} />
          The registers
        </button>
      </header>

      {/* ============================================================= the room */}
      <div className="di-body">
        <div className="di-stage">
          {items.length === 0 ? (
            <Empty
              icon="district"
              title="This district has nothing standing in it."
              body="No colleague works here, no reading reports on it and no envelope pays for it. The district exists — a process declared it — and nothing has been put inside it yet."
            />
          ) : (
            <Room
              items={items}
              selectedKey={selected}
              hoveredKey={hovered}
              onHover={setHovered}
              onSelect={open}
            />
          )}
        </div>

        {/* ------------------------------------------------------ the reveal
            Everything the old surface showed at once, shown when asked for. */}
        <aside className="di-reveal" aria-live="polite">
          {selected === null && (
            <RoomLegend
              district={district}
              wire={wire}
              handsRaised={handsRaised}
              measurable={measurable.length}
            />
          )}

          {colleague && (
            <ColleaguePanel
              colleague={colleague}
              district={district}
              onClose={() => setSelected(null)}
              onOpenDossier={onOpenDossier}
              onEcho={onEcho}
            />
          )}

          {selected === FIXTURE.kpi && (
            <KpiPanel plinth={district.kpi.plinth} onClose={() => setSelected(null)} />
          )}

          {selected === FIXTURE.treasury && district.treasury !== null && (
            <TreasuryPanel
              treasury={district.treasury}
              onClose={() => setSelected(null)}
            />
          )}

          {selected === FIXTURE.runs && (
            <RunsPanel district={district} onClose={() => setSelected(null)} />
          )}
        </aside>
      </div>

      {/* ----------------------------------------------------------- traffic
          A readout, not a control. It used to echo "descended to the ledger"
          and descend nowhere — an echo for an act that did not happen, which
          is worse than no affordance (the Terrace settled this for the estate).
          `<dl>` because these are label–value pairs (§6). */}
      <footer className="di-traffic">
        <dl className="di-traffic-list">
          {(
            [
              ["IN · 1H", String(district.traffic.in_1h)],
              ["OUT · 1H", String(district.traffic.out_1h)],
              ["PARKED", String(district.traffic.parked)],
            ] as const
          ).map(([label, value]) => (
            <div className="di-traffic-item" key={label}>
              <dt className="t-eyebrow">{label}</dt>
              <dd className="t-mono di-traffic-value">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="di-traffic-hint t-mono">click a structure to open it</p>
      </footer>
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

/** With nothing selected the panel explains the room rather than sitting empty.
 *  It also carries the wire reading, because this room's numbers are the ones
 *  that look calm when they are merely old (S3). */
function RoomLegend({
  district,
  wire,
  handsRaised,
  measurable,
}: {
  district: EstateDistrict;
  wire: WireState;
  handsRaised: number;
  measurable: number;
}) {
  const people = district.colleagues.length;
  const readings = district.kpi.plinth.length;
  const who =
    people === 0
      ? "Nobody works here yet"
      : `${people} colleague${people === 1 ? "" : "s"} work${people === 1 ? "s" : ""} here`;
  const what =
    readings === 0
      ? ""
      : `, and ${readings} reading${readings === 1 ? "" : "s"} report${
          readings === 1 ? "s" : ""
        } on the place`;
  return (
    <div className="di-legend vh-enter-fade">
      <span className="t-eyebrow">THE ROOM</span>
      <p className="t-narrative di-legend-body">
        {who}
        {what}. Click any structure to open it.
      </p>
      <hr className="m-rule-fade" />
      <dl className="di-legend-list">
        {[
          ["Back row", "the instruments — the readings, the envelope, the table of runs"],
          ["Front row", "the colleagues, each at their own workplace"],
          ["A gold shaft", "a colleague with a hand raised"],
        ].map(([k, v]) => (
          <div className="di-legend-row" key={k}>
            <dt className="t-eyebrow">{k}</dt>
            <dd className="di-legend-val">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="di-legend-foot t-mono">
        {measurable} of {district.kpi.plinth.length} readings measurable · {handsRaised}{" "}
        hand{handsRaised === 1 ? "" : "s"} raised
      </p>
      {wire.status === "stale" && (
        <p className="di-stale t-mono" role="status">
          <span className="m-lamp" data-negative aria-hidden="true" />
          The estate has stopped sending updates, so these numbers are the last
          ones it sent.
          {wire.retryInSeconds !== null && ` Trying again in ${wire.retryInSeconds}s.`}
        </p>
      )}
    </div>
  );
}

function ColleaguePanel({
  colleague,
  district,
  onClose,
  onOpenDossier,
  onEcho,
}: {
  colleague: EstateColleague;
  district: EstateDistrict;
  onClose: () => void;
  onOpenDossier?: (id: string) => void;
  onEcho: (msg: string) => void;
}) {
  return (
    <div className="di-panel vh-enter">
      <PanelHead
        eyebrow={`COLLEAGUE · ${district.name.toUpperCase()}`}
        title={colleague.name}
        onClose={onClose}
      />

      <div className="di-who">
        <div className="m-portrait-well di-who-portrait">
          {/* Keyed through `artKeyFor` so a colleague is filed under the same
              art key here and on her dossier. The estate projects
              `display_name or name` into one field, so a colleague with a
              display name falls through to the procedural bust — recorded as a
              gap rather than papered over with a second key derivation. */}
          <Portrait
            id={artKeyFor(colleague.name)}
            size={72}
            title={`${colleague.name} — a generated portrait, not a photograph`}
          />
        </div>
        <dl className="di-who-facts">
          {[
            ["Entity", colleague.entity_id.slice(0, 8)],
            ["Autonomy", colleague.autonomy],
            ["State", colleague.state],
          ].map(([k, v]) => (
            <div className="di-fact" key={k}>
              <dt className="t-eyebrow">{k}</dt>
              <dd className="t-mono di-fact-val">{v}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="m-well di-state">
        {colleague.hand_raised ? (
          <p className="di-state-line">
            <span className="m-lamp" data-lit data-breathing />
            <span className="di-state-gold">She is waiting for you.</span> Her card
            is in the tray.
          </p>
        ) : colleague.state === "running" ? (
          <p className="di-state-line">
            <span className="m-lamp" data-positive />
            She has work running now.
          </p>
        ) : (
          <p className="di-state-line">
            <span className="m-lamp" />
            Idle — nothing has come in for her.
          </p>
        )}
      </div>

      {/* Two absences, stated where the fixture used to print them. Neither is
          a defect of this district: the platform models neither. */}
      <p className="di-panel-note t-mono">
        The estate keeps no rank beyond the autonomy band, and no run records in
        words what it is doing — so there is no standing and no “now” to show
        here.
      </p>

      <div className="di-panel-acts">
        <button
          className="m-btn"
          onClick={() => {
            onEcho(`opened ${colleague.name}’s dossier`);
            onOpenDossier?.(colleague.entity_id);
          }}
        >
          <Icon name="colleague" size={13} />
          Open her dossier
        </button>
      </div>
    </div>
  );
}

/**
 * The plinth, with no target and therefore no meter.
 *
 * The obelisk used to stand against a tick. `PlinthKpi` carries `{value,
 * measurable, unit}` and the KPI registry declares no target anywhere on the
 * platform — the same hole that keeps `fog` off the weather and keeps a dial
 * off the dossier's reliability block. A track drawn to a number this file
 * chose would be a working feature over a known gap (§7.4), so the readings are
 * listed and the absence is stated once.
 */
function KpiPanel({ plinth, onClose }: { plinth: PlinthKpi[]; onClose: () => void }) {
  return (
    <div className="di-panel vh-enter">
      <PanelHead eyebrow="THE READINGS" title="What reports on this district" onClose={onClose} />

      <dl className="di-kpis">
        {plinth.map((kpi) => {
          const figure = formatMeasure(kpi);
          return (
            <div className="di-kpi" key={kpi.kpi_key}>
              <dt className="di-kpi-name">
                {kpi.display_name}
                <span className="t-mono di-kpi-key">{kpi.kpi_key}</span>
              </dt>
              <dd>
                {/* §7.1 twice over. A figure appears only when there is one;
                    the two absences are different facts and get different
                    sentences, exactly as the wire keeps them apart. */}
                {figure !== null ? (
                  <span className="t-figure di-kpi-figure">{figure}</span>
                ) : !kpi.measurable ? (
                  <span className="di-kpi-absent">
                    <span className="m-lamp" aria-hidden="true" />
                    never measured — no snapshot has been taken of this yet
                  </span>
                ) : (
                  <span className="di-kpi-absent">
                    <span className="m-lamp" aria-hidden="true" />
                    not measurable today — the inputs it needs were missing
                  </span>
                )}
              </dd>
            </div>
          );
        })}
      </dl>

      <p className="di-panel-note t-mono">
        No target is drawn because none exists. The KPI registry declares a
        baseline and no target, so there is nothing on the platform to hold these
        readings against — and a meter would have to invent the line it is
        measuring to.
      </p>
    </div>
  );
}

function TreasuryPanel({
  treasury,
  onClose,
}: {
  treasury: NonNullable<EstateDistrict["treasury"]>;
  onClose: () => void;
}) {
  const { spent, cap, reserve_protected } = treasury;
  /* Derived, and guarded: a zero cap would make the gauge `NaN%` wide. A
     district whose envelope is zero has no proportion to draw, and says so. */
  const proportion = cap > 0 ? Math.min(1, spent / cap) : null;

  return (
    <div className="di-panel vh-enter">
      <PanelHead eyebrow="THE VAULT" title="The envelope" onClose={onClose} />

      {proportion !== null && (
        <div className="di-gauge m-well" role="presentation">
          <span className="di-gauge-spent" style={{ width: `${proportion * 100}%` }} />
        </div>
      )}

      <dl className="di-who-facts di-treasury-facts">
        {[
          ["Spent", grouped(spent)],
          ["Envelope", grouped(cap)],
        ].map(([k, v]) => (
          <div className="di-fact" key={k}>
            <dt className="t-eyebrow">{k}</dt>
            <dd className="t-mono di-fact-val">{v}</dd>
          </div>
        ))}
        <div className="di-fact">
          <dt className="t-eyebrow">Reserve</dt>
          <dd className="t-mono di-fact-val">
            {reserve_protected ? "protected" : "none set"}
          </dd>
        </div>
      </dl>

      <p className="di-panel-note t-mono">
        {reserve_protected
          ? "Work stops before the reserve is spent, so a runaway process cannot empty the envelope. The projection reports only that a reserve is set — not how much — so it is stated rather than drawn on the gauge."
          : "No reserve is set on this envelope, so there is no floor under it."}
      </p>
      <p className="di-panel-note t-mono">
        These figures carry no currency. The projection states none, so none is
        printed — the envelope is a number the platform keeps, not a sum this
        screen has decided the unit of.
      </p>
    </div>
  );
}

/**
 * The table of runs.
 *
 * Mounted on selection rather than with the surface, and that is deliberate:
 * `GET /ai/executions` takes **no parameters at all** and returns every root
 * execution the company ever ran (gap R-4-P-3), so it is read when the table is
 * opened and not on every walk through the district. The narrowing to this
 * district happens here because the backend offers no way to ask for it.
 */
function RunsPanel({
  district,
  onClose,
}: {
  district: EstateDistrict;
  onClose: () => void;
}) {
  const executions = useResource(fetchExecutions);

  const ids = useMemo(
    () => new Map(district.colleagues.map((c) => [c.entity_id, c.name])),
    [district],
  );

  const SHOWN = 40;

  const mine = useMemo(() => {
    if (executions.phase !== "ready") return [];
    return executions.value
      .filter((run) => ids.has(run.entity_id))
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [executions, ids]);

  const rows = mine.slice(0, SHOWN);

  return (
    <div className="di-panel vh-enter">
      <PanelHead eyebrow="THE TABLE" title="Runs in this district" onClose={onClose} />

      {executions.phase === "pending" ? (
        <Scaffold label="The table of runs">
          <div className="m-well di-run-list">
            <Lines n={5} />
          </div>
        </Scaffold>
      ) : executions.phase === "failed" ? (
        <Failed
          alone={false}
          what="the table of runs"
          reason={executions.reason}
          onRetry={executions.retry}
        />
      ) : rows.length === 0 ? (
        <Empty
          icon="clock"
          title="No run has been recorded here."
          body="A run appears the moment a colleague in this district is asked to do something. Nothing has been asked of anyone here yet, or everything that was has already been cleared out of the record."
        />
      ) : (
        <>
          <ul className="di-run-list m-well" data-deep>
            {rows.map((run) => (
              <RunRow key={run.id} run={run} who={ids.get(run.entity_id)} />
            ))}
          </ul>
          <p className="di-panel-note t-mono">
            No run records in words what it is doing, so each is named by its
            colleague and its id. Nothing here can be paused: the platform ends a
            run outright or lets it finish, and there is no hold in between.
            {/* A cap that is not said is a cap that reads as a total. */}
            {mine.length > SHOWN &&
              ` Showing the ${SHOWN} most recent of ${mine.length}.`}
          </p>
        </>
      )}
    </div>
  );
}

function RunRow({ run, who }: { run: RunSummary; who: string | undefined }) {
  const active = ACTIVE.has(run.status.toUpperCase());
  const failed = FAILED.has(run.status.toUpperCase());
  return (
    <li className="di-run">
      {/* Lamp plus the wire's own word — never colour alone (§4), and never
          `data-lit`, which is gold. A run that is merely working is not "this
          needs you"; the fixture lit one and that was a gold budget spent on
          "something is happening", which §2.1 names as exactly what gold is
          not. Sage for running, terracotta for failed, unlit for the rest. */}
      <span
        className="m-lamp"
        data-positive={active || undefined}
        data-negative={failed || undefined}
        aria-hidden="true"
      />
      <span className="di-run-open">
        <span className="di-run-doing">{who ?? run.entity_id.slice(0, 8)}</span>
        <span className="t-mono di-run-id">{run.id.slice(0, 8)}</span>
      </span>
      <span className="t-mono di-run-elapsed">{run.status.toLowerCase()}</span>
      <span className="t-mono di-run-when">{stamp(run.created_at)}</span>
    </li>
  );
}

/**
 * The pending state (D7 §3.1): the room's own structure, standing, with the
 * words not yet in it. No spinner — this is one of the seventeen.
 *
 * Plates first, bars inside them: `vh-skeleton`'s ground is a ~6/255 delta on
 * the raw canvas, so a bar drawn on the page background is invisible.
 */
function DistrictScaffold() {
  return (
    <section className="di">
      <Scaffold label="This district">
        <div className="di-scaffold">
          <div className="di-scaffold-head m-plate">
            <Bar width="xs" />
            <Bar width="sm" tall />
          </div>
          <div className="di-scaffold-body">
            <div className="di-scaffold-stage m-plate">
              <Bar width="md" tall />
            </div>
            <div className="di-scaffold-panel m-plate">
              <Bar width="sm" />
              <Lines n={4} />
            </div>
          </div>
        </div>
      </Scaffold>
    </section>
  );
}
