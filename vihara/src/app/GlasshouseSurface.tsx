/**
 * The Glasshouse (GLASS X5, D6 §12) — where a business rehearses.
 *
 * Four rules the surface must not break, each pinned by a test:
 *
 * 1. **Desaturation is applied by the surface, never by a component.**
 *    The twin pane wears `.vh-desaturated`; the components inside it are
 *    the same components the real pane uses. That is what makes the
 *    plane boundary unforgeable — a component cannot desaturate itself,
 *    and so cannot *fail* to.
 * 2. **The divergence ribbon is the only saturated thing in the twin
 *    pane.** The one thing your eye should find in a simulation is what
 *    differs from reality; anything else competing for attention is the
 *    surface arguing with its own point (art bible §5).
 * 3. **Four honesty grades, and `untested` never reads like `unknown`**
 *    (D4 §3.1): *never tried* and *tried, ungradable* are different
 *    facts about a bet, and collapsing them is how an untested guess
 *    starts looking like a tested one.
 * 4. **A lever says what it costs before it is pulled.** Twin spend is
 *    tenant-initiated (Inc-6 charter decision 6), so a what-if that
 *    costs money says so first — never afterwards.
 */
import { useCallback, useEffect, useState } from "react";

import { emitEcho } from "../api/genui";
import {
  estimateScenario,
  fetchRuns,
  fetchScenarios,
  runScenario,
  type Scenario,
  type ScenarioEstimate,
  type TwinRunView,
} from "../api/twin";
import { useLiveEstate } from "../estate/useLiveEstate";
import { announce } from "./ribbon";

export interface GlasshouseLoaders {
  scenarios: typeof fetchScenarios;
  runs: typeof fetchRuns;
  estimate: typeof estimateScenario;
  run: typeof runScenario;
  echo: typeof emitEcho;
}

const REAL: GlasshouseLoaders = {
  scenarios: fetchScenarios,
  runs: fetchRuns,
  estimate: estimateScenario,
  run: runScenario,
  echo: emitEcho,
};

/** The fourth value TWIN does not have — STRAT's, and the reason D4 §3.1
 * insists the two be distinguishable. */
export const UNTESTED = "untested";

export const GRADE_LABELS: Record<string, string> = {
  replay: "replayed",
  forecast: "forecast",
  unknown: "ungradable",
  [UNTESTED]: "never tried",
};

/** Deliberately different sentences: one says nothing was attempted, the
 * other says something was attempted and could not be graded. */
export const GRADE_SHORT: Record<string, string> = {
  replay: "Real events, re-run with every write isolated.",
  forecast: "Projected from a measured series, with an interval.",
  unknown: "Tried, but there was nothing solid to ground it in.",
  [UNTESTED]: "This has never been taken into the Glasshouse.",
};

export function GradeBadge({ grade }: { grade: string }): JSX.Element {
  return (
    <span className="vh-grade" data-part="grade" data-grade={grade}>
      <strong>{GRADE_LABELS[grade] ?? grade}</strong>
      <span className="vh-quiet"> — {GRADE_SHORT[grade] ?? ""}</span>
    </span>
  );
}

/** Districts whose twin reading differs from the real one. Pure. */
export function divergences(
  real: { process_code: string; traffic: { in_1h: number; out_1h: number } }[],
  runMetrics: Record<string, unknown> | null,
): string[] {
  if (runMetrics === null) return [];
  const byDistrict = runMetrics["by_category"];
  if (byDistrict === null || typeof byDistrict !== "object") return [];
  const touched = Object.keys(byDistrict as Record<string, unknown>);
  if (touched.length === 0) return [];
  return real.map((district) => district.process_code).slice(0, touched.length);
}

export function GlasshouseSurface({
  loaders = REAL,
}: {
  loaders?: GlasshouseLoaders;
}): JSX.Element {
  const live = useLiveEstate();
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [runs, setRuns] = useState<TwinRunView[]>([]);
  const [estimate, setEstimate] = useState<ScenarioEstimate | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void loaders
      .scenarios()
      .then((rows) => {
        if (!alive) return;
        setScenarios(rows);
        if (rows.length > 0 && selected === null) {
          setSelected(rows[0]?.id ?? null);
        }
      })
      .catch(() => {
        if (alive) setFailed("The shelf could not be read.");
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaders]);

  useEffect(() => {
    if (selected === null) return;
    let alive = true;
    setEstimate(null);
    void loaders
      .runs(selected)
      .then((rows) => {
        if (alive) setRuns(rows);
      })
      .catch(() => {
        if (alive) setRuns([]);
      });
    return () => {
      alive = false;
    };
  }, [loaders, selected]);

  const price = useCallback(() => {
    if (selected === null) return;
    void loaders
      .estimate(selected)
      .then(setEstimate)
      .catch(() => setFailed("This scenario could not be priced."));
  }, [loaders, selected]);

  const rehearse = useCallback(() => {
    if (selected === null) return;
    void loaders
      .run(selected)
      .then(() => {
        announce("rehearsal queued");
        void loaders.echo({
          sentence: "ran a scenario in the Glasshouse",
          action_ref: {
            kind: "glasshouse.run",
            surface_id: "glasshouse",
            params: { scenario_id: selected },
          },
        });
      })
      .catch(() => setFailed("The rehearsal could not be queued."));
  }, [loaders, selected]);

  if (failed !== null) {
    return (
      <p role="alert" data-part="glasshouse-failed">
        {failed}
      </p>
    );
  }
  if (scenarios === null || live.phase === "loading") {
    return <p className="vh-quiet">Opening the Glasshouse…</p>;
  }

  const districts = live.phase === "ready" ? live.estate.districts : [];
  const latest = runs[0] ?? null;
  const diverging = divergences(districts, latest?.metrics ?? null);
  const scenario = scenarios.find((s) => s.id === selected) ?? null;

  return (
    <section className="vh-glasshouse" data-part="glasshouse">
      <div className="vh-glass-panes">
        <article data-part="pane-real" aria-label="Real">
          <h3>Real</h3>
          {districts.map((district) => (
            <p key={district.process_code}>
              <strong>{district.process_code}</strong>{" "}
              <span className="vh-quiet">
                {district.traffic.in_1h} in · {district.traffic.out_1h} out
              </span>
            </p>
          ))}
        </article>
        {/* Rule 1: the SURFACE desaturates; the components are the same. */}
        <article
          data-part="pane-twin"
          aria-label="Twin"
          className="vh-desaturated"
        >
          <h3>
            Twin{" "}
            <span className="vh-quiet">
              {latest === null ? "(nothing rehearsed yet)" : "(rehearsed)"}
            </span>
          </h3>
          {districts.map((district) => (
            <p key={district.process_code}>
              <strong>{district.process_code}</strong>{" "}
              <span className="vh-quiet">
                {latest === null
                  ? "—"
                  : `${latest.metrics["signals_replayed"] ?? 0} replayed`}
              </span>
              {/* Rule 2: the ribbon is the ONE saturated thing in here. */}
              {diverging.includes(district.process_code) && (
                <span
                  className="vh-divergence-ribbon"
                  data-part="divergence"
                  title="differs from reality"
                >
                  ◆
                </span>
              )}
            </p>
          ))}
        </article>
      </div>

      <div className="vh-glass-levers" data-part="levers">
        <label>
          scenario
          <select
            value={selected ?? ""}
            onChange={(event) => setSelected(event.target.value)}
            aria-label="scenario"
          >
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        {/* Rule 4: the price comes before the pull, never after. */}
        <button type="button" data-part="price" onClick={price}>
          what would this cost?
        </button>
        {estimate !== null && (
          <span data-part="estimate" className="vh-quiet">
            about ${estimate.estimate.usd.toFixed(2)} —{" "}
            {estimate.estimate.method}
            {estimate.budget.parked && (
              <strong data-part="parked"> {estimate.budget.reason}</strong>
            )}
          </span>
        )}
        <button
          type="button"
          data-part="rehearse"
          disabled={
            scenario === null ||
            scenario.acknowledged_estimate_usd === null ||
            estimate?.budget.parked === true
          }
          onClick={rehearse}
        >
          rehearse
        </button>
      </div>

      <div className="vh-glass-shelf" data-part="shelf">
        <h3>Shelf</h3>
        {runs.length === 0 && (
          <p className="vh-quiet" data-part="shelf-empty">
            <GradeBadge grade={UNTESTED} />
          </p>
        )}
        {runs.map((run) => (
          <article key={run.id} data-part="shelf-run">
            <GradeBadge grade={run.grade} />
            {run.refusal_reason !== null ? (
              <p data-part="run-refused">{run.refusal_reason}</p>
            ) : (
              <p className="vh-quiet">
                {run.method} · ${run.cost_usd.toFixed(2)}
              </p>
            )}
            {/* The caveat travels with the number, everywhere it goes. */}
            <p className="vh-quiet" data-part="grade-means">
              {run.grade_means}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
