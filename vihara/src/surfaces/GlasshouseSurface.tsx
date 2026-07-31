import { useEffect, useRef, useState } from "react";

import { Icon } from "../components/Icon";
import { Room, type RoomItem } from "../world/Room";
import { Bar, Empty, Failed, Lines, Scaffold, reasonOf, useChoice, useResource } from "../lifecycle";
import {
  estimateScenario,
  fetchRuns,
  fetchScenarios,
  runScenario,
  type Scenario,
  type ScenarioEstimate,
  type TwinRunView,
} from "../api/twin";
import { GradeSeal, grouped, honestyOf, type Grade } from "./BoardroomSurface";
import "./glasshouse.css";

/**
 * The Glasshouse · depth 2 · W+S, desaturated (D6 §12) — on `/ai/twin/*`
 * (R-4 part W).
 *
 * Two panes, and the whole surface hangs on one property: **the twin is the
 * real, drained.** Not recoloured — the same room with the life taken out of
 * it. A blue twin would say "different place"; a drained twin says "not yet
 * real". Draining is applied at the plane boundary by the renderer (`Room`'s
 * `drained` prop) and never chosen per element, which is what makes it
 * unforgeable: a twin-derived component cannot be styled to look real.
 *
 * ## The one permitted loading state, and why it is words
 *
 * D7 §3.1 names this the **only** surface allowed a visible loading state,
 * because a twin run is genuinely slow and pretending otherwise would be the
 * lie. It is spent here and nowhere else, and it is spent on a **sentence**
 * rather than a spinner: a spinner says "wait" and tells you nothing, and what
 * an owner needs to know is roughly how long and what is happening. The first
 * paint is still a scaffold like every other room — the exemption is for the
 * run, not for the load.
 *
 * ## Running is three calls, and two of its refusals are results
 *
 * Verified end to end against the shipping backend before this surface was
 * wired, not read off the router: create (201) → `/estimate` → `/run` (202) →
 * the arq worker → `/scenarios/{id}/runs` returning a graded `replay` with the
 * engine's own `grade_means`.
 *
 *  - **`/run` before `/estimate` is a 409** naming the rule: a what-if should
 *    never cost money the owner has not seen first (charter decision 6). So the
 *    button prices first, always, and shows the price it just learned.
 *  - **Over the daily cap the scenario parks** — `budget.admitted` is false
 *    with a reason. That is content, not an error, and nothing is queued.
 *  - **An unreachable arq worker is a 503**, with "nothing was spent" in the
 *    message. The worker is a known single point of failure in this platform,
 *    and this is the surface where that has to be visible rather than a
 *    scenario that silently never runs.
 *
 * ## What the wiring took away, and why none of it is a redesign
 *
 * §7.1 — a binding that cannot be answered renders **nothing**:
 *
 *  - **The lever sliders are gone.** `GET /ai/twin/scenarios` does not return a
 *    scenario's levers, and no endpoint writes them: the only place levers are
 *    ever accepted is `POST /ai/twin/scenarios`, at creation. Sliders over a
 *    value the surface cannot read and cannot save would be a control that
 *    does nothing, which is worse than no control. The panel now shows the
 *    **runs**, which is what `GET /scenarios/{id}/runs` is for.
 *  - **The real pane has no baseline.** `TwinRun.is_baseline` exists, is
 *    indexed, and is read by the cost module — and **nothing in the platform
 *    ever writes it `True`**. So there is no cached baseline replay to put
 *    opposite the rehearsal, the divergence ribbon has no second number, and
 *    both say so. The ribbon renders its absent state rather than being drawn
 *    between one number and nothing, which is the failure it was designed to
 *    avoid; its two populated parts are still in `glasshouse.css`, waiting for
 *    a baseline writer to give them something to hold.
 *  - **The spend block waits for a price.** `budget.spent_today_usd` and
 *    `daily_cap_usd` arrive on the estimate response and nowhere else, so
 *    before you have priced something there is no figure — never a zero.
 *  - **Promotion is drawn and not taken here.** `POST /ai/twin/runs/{id}/promote`
 *    needs an `entity_id` and a charter `field` to amend; this room holds
 *    neither. The chain is a true statement about the route and stays; the act
 *    belongs where the colleague is.
 *
 * Cost is visible because twin spend is tenant-initiated (charter decision 6):
 * a cost the tenant chose to incur is a cost they are owed a number for. The
 * figures are printed as **USD** because the fields name their own unit
 * (`cost_usd`, `estimate.usd`) — unlike the tray's amounts, where no currency
 * was ever stated and none is therefore shown.
 */

/** How long the run's own words promise, and how long the poll will wait. */
const RUN_WORDS = "running the twin — about a minute";
const POLL_EVERY_MS = 4000;
const POLL_FOR_MS = 150_000;

/** The metric a run leads with, in the order an owner reads them: what was
 *  real first. Never invented — the first of these the run actually carries. */
const HEADLINE: readonly string[] = ["signals_replayed", "runs_executed", "simulated_calls"];

const METRIC_WORD: Record<string, string> = {
  signals_replayed: "real signals replayed",
  runs_executed: "agent runs inside the glass",
  simulated_calls: "external calls intercepted",
  external_effects: "effects that escaped",
};

function metricNumber(metrics: Record<string, unknown>, key: string): number | null {
  const value = metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** The engine's grade, with its own sentence — which, unlike a Planning
 *  record's, *is* on this payload (`grade_means`). */
function gradeOf(run: TwinRunView): Grade | null {
  const grade = honestyOf(run.grade);
  if (grade === null) return null;
  return {
    grade,
    twinRunId: run.id,
    means: run.grade_means === "" ? null : run.grade_means,
  };
}

/** The stamp is naive UTC on the wire (`datetime.utcnow`, no zone), and `Date`
 *  reads a naive ISO string as local — a five-and-a-half-hour lie in IST. */
function clockOf(iso: string | null): string | null {
  if (iso === null) return null;
  const stamped = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const at = new Date(stamped);
  if (Number.isNaN(at.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(at);
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export function GlasshouseSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const scenarios = useResource(fetchScenarios);

  if (scenarios.phase === "pending") return <GlasshouseScaffold />;

  if (scenarios.phase === "failed") {
    return (
      <section className="gh">
        <Failed
          what="the Glasshouse shelf"
          reason={scenarios.reason}
          onRetry={scenarios.retry}
        />
      </section>
    );
  }

  return <Shelf scenarios={scenarios.value} onEcho={onEcho} />;
}

function Shelf({
  scenarios,
  onEcho,
}: {
  scenarios: Scenario[];
  onEcho: (msg: string) => void;
}) {
  /* L1: was `useState(SCENARIOS[0]!.id)` — a TypeError before render on an
     estate that has never run a twin, which is every estate on its first day. */
  const { chosen, chosenId, choose } = useChoice(scenarios, (s) => s.id);

  /* L2. Both panes, the ribbon, the shelf and the runs are all one scenario's —
     there is no partial Glasshouse to draw, so with nothing on the shelf the
     room says what it is for, and where a scenario comes from. */
  if (chosen === undefined) {
    return (
      <section className="gh">
        <Empty
          alone
          icon="trend"
          title="Nothing has been tried in here yet."
          body="The Glasshouse holds a drained copy of the estate, so a plan can be run against it without touching anything real. A scenario appears here once one is sent down from the Boardroom — take a proposition to the Glasshouse and it lands on this shelf, unpriced, waiting for you to say go."
        />
      </section>
    );
  }

  return (
    <ScenarioView
      /* Keyed, so the runs read below remounts with a fresh loader rather than
         holding the previous scenario's runs — `useResource` captures its
         reader once, on purpose. */
      key={chosen.id}
      scenario={chosen}
      shelf={scenarios}
      activeId={chosenId}
      onChoose={choose}
      onEcho={onEcho}
    />
  );
}

function ScenarioView({
  scenario,
  shelf,
  activeId,
  onChoose,
  onEcho,
}: {
  scenario: Scenario;
  shelf: Scenario[];
  activeId: string | undefined;
  onChoose: (id: string) => void;
  onEcho: (msg: string) => void;
}) {
  const runs = useResource(() => fetchRuns(scenario.id));

  const [estimate, setEstimate] = useState<ScenarioEstimate | null>(null);
  /** The one permitted visible loading state (D7 §3.1), in words. */
  const [running, setRunning] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  /** The poll gave up before a run appeared. Not a failure — the worker is a
   *  known single point of failure and a queued scenario stays queued. */
  const [stillQueued, setStillQueued] = useState(false);

  /* The poll outlives a click and must not outlive the room. Set on mount as
     well as cleared on unmount, because a StrictMode double-mount would
     otherwise leave a live surface flagged dead. */
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  /** The freshest way to re-read the runs. Held in a ref because the poll is
   *  inside an async loop that started several renders ago. */
  const reload = useRef<() => void>(() => undefined);
  useEffect(() => {
    if (runs.phase !== "pending") reload.current = runs.retry;
  });

  const list = runs.phase === "ready" ? runs.value : NO_RUNS;
  /* Nothing in the platform writes `is_baseline`. The lookup stays because the
     column is real and read elsewhere; today it is always `undefined`, and the
     real pane says so rather than borrowing the rehearsal's own number. */
  const baseline = list.find((run) => run.is_baseline);
  const latest = list.find((run) => !run.is_baseline);

  async function runIt(): Promise<void> {
    if (running) return;
    setProblem(null);
    setStillQueued(false);
    setRunning(true);
    const before = list.length;
    try {
      /* Price first, always. `/run` 409s without an acknowledged estimate, and
         the rule behind that 409 is the one this surface exists to keep: a
         tenant should never learn a what-if's price afterwards. */
      const priced = await estimateScenario(scenario.id);
      if (!alive.current) return;
      setEstimate(priced);

      if (!priced.budget.admitted) {
        /* Parked, not failed. The scenario keeps its place and resumes when
           the daily budget does. */
        setProblem(priced.budget.reason);
        return;
      }

      await runScenario(scenario.id);
      if (!alive.current) return;
      onEcho(`ran ${scenario.name} in the Glasshouse`);

      const deadline = Date.now() + POLL_FOR_MS;
      for (;;) {
        await sleep(POLL_EVERY_MS);
        if (!alive.current) return;
        let seen = before;
        try {
          seen = (await fetchRuns(scenario.id)).length;
        } catch {
          /* A poll that failed is not the run failing. Keep waiting; the
             deadline below is what ends this, and the reload after it is what
             tells the truth. */
        }
        if (!alive.current) return;
        if (seen > before) {
          reload.current();
          return;
        }
        if (Date.now() > deadline) {
          setStillQueued(true);
          return;
        }
      }
    } catch (thrown) {
      if (alive.current) setProblem(reasonOf(thrown));
    } finally {
      if (alive.current) setRunning(false);
    }
  }

  const spend = estimate?.budget ?? null;
  const grade = latest === undefined ? null : gradeOf(latest);

  return (
    <section className="gh">
      {/* ------------------------------------------------------------- header */}
      <header className="gh-head">
        <div className="gh-head-lead">
          <span className="t-eyebrow">THE GLASSHOUSE · SIMULATION</span>
          <h1 className="gh-title t-display">Try it here first</h1>
          <p className="t-narrative gh-lead">
            Nothing in this room can touch the real. Everything you see on the
            right is drained, and it stays drained until it is promoted.
          </p>
        </div>

        {/* No figure until something has been priced. A "₹0 this month" over an
            estate that has simply not asked is the invented number §7.1 puts
            first. */}
        {spend !== null && (
          <div className="gh-spend m-well">
            <span className="t-eyebrow">TODAY</span>
            <span className="gh-spend-figure t-mono">
              USD {grouped(spend.spent_today_usd)} of {grouped(spend.daily_cap_usd)}
            </span>
            <p className="gh-spend-note t-mono">{spend.reason}</p>
          </div>
        )}
      </header>

      {/* ============================================================ the panes */}
      <div className="gh-panes">
        <Pane
          side="real"
          eyebrow="REAL · BASELINE"
          figure={baseline === undefined ? null : headlineOf(baseline)}
          label={baseline === undefined ? "no baseline replay" : (baseline.method ?? "")}
          items={baseline === undefined ? [] : roomFor(baseline, "real")}
          absentNote={
            baseline === undefined
              ? "There is no baseline replay to stand here. The platform records whether a run is a baseline and nothing ever marks one, so the estate has never cached the “before” this rehearsal would be measured against. I am not going to put the rehearsal's own number on this side."
              : undefined
          }
        />

        {/* The divergence ribbon — sanctioned gold inside the twin, and the only
            thing here asking to be looked at. Absent when there is nothing to
            compare, because a ribbon between one number and nothing is a ribbon
            that invents the second number. */}
        <div className="gh-ribbon" aria-hidden="true">
          <span className="gh-ribbon-absent t-mono">no reading to compare</span>
        </div>

        <Pane
          side="twin"
          eyebrow="TWIN · DRAINED"
          figure={latest === undefined ? null : headlineOf(latest)}
          label={latest === undefined ? "nothing has run" : (latest.method ?? "")}
          items={latest === undefined ? [] : roomFor(latest, "twin")}
          absentNote={
            latest === undefined
              ? "This scenario has never been run, so there is no reading. I am not going to put a number here."
              : (latest.refusal_reason ?? undefined)
          }
        />
      </div>

      {/* ============================================================ the shelf */}
      <div className="gh-lower">
        <section className="gh-shelf" aria-label="The scenario shelf">
          <header className="gh-block-head">
            <span className="t-eyebrow">THE SHELF</span>
            <span className="t-mono gh-block-note">
              {shelf.length} {shelf.length === 1 ? "scenario" : "scenarios"} · each
              priced before it is run
            </span>
          </header>
          <div className="gh-shelf-list">
            {shelf.map((item) => (
              <button
                key={item.id}
                className="gh-card m-plate"
                data-active={item.id === activeId || undefined}
                onClick={() => onChoose(item.id)}
              >
                <span className="gh-card-head">
                  <span className="t-mono gh-card-id">{item.kind}</span>
                  <span className="m-chip">{item.status}</span>
                </span>
                <span className="gh-card-label t-display">{item.name}</span>
                {item.scope.window_days !== undefined && (
                  <span className="gh-card-q">
                    a {item.scope.window_days}-day window
                    {item.scope.objects !== undefined && item.scope.objects.length > 0
                      ? ` over ${item.scope.objects.join(", ")}`
                      : ""}
                  </span>
                )}
                {/* A null estimate renders as nothing — never USD 0. An
                    unpriced scenario has not been priced, which is not the same
                    as costing nothing. */}
                {item.acknowledged_estimate_usd !== null && (
                  <span className="t-mono gh-card-cost">
                    priced at USD {grouped(item.acknowledged_estimate_usd)}
                  </span>
                )}
              </button>
            ))}
          </div>
        </section>

        {/* ------------------------------------------------------- the controls */}
        <section className="gh-controls" aria-label="Runs, grade and promotion">
          {/* -------------------------------------------------------- the runs */}
          <div className="gh-panel m-plate">
            <header className="gh-block-head">
              <span className="t-eyebrow">RUNS</span>
              <span className="t-mono gh-block-note">newest first</span>
            </header>

            {runs.phase === "pending" && (
              <div className="gh-ghost" aria-hidden="true">
                <Lines n={2} />
              </div>
            )}

            {runs.phase === "failed" && (
              <Failed
                what="this scenario's runs"
                alone={false}
                reason={runs.reason}
                onRetry={runs.retry}
              />
            )}

            {runs.phase === "ready" &&
              (list.length === 0 ? (
                <p className="gh-blocked t-mono">
                  Nothing has been rehearsed here yet. A scenario sits on the
                  shelf until you price it and say go — the estate does not spend
                  your money on a what-if by itself.
                </p>
              ) : (
                <ol className="gh-runs">
                  {list.map((run) => {
                    const seal = gradeOf(run);
                    const at = clockOf(run.started_at);
                    return (
                      <li className="gh-run" key={run.id}>
                        <span className="gh-run-top">
                          {seal !== null && <GradeSeal grade={seal} compact />}
                          {at !== null && <span className="t-mono gh-run-at">{at}</span>}
                        </span>
                        {run.method !== null && (
                          <span className="gh-run-method t-mono">{run.method}</span>
                        )}
                        {/* A refusal is a result, not an error to be swallowed. */}
                        {run.refusal_reason !== null && (
                          <span className="gh-run-refused t-mono">
                            <Icon name="alert" size={11} />
                            {run.refusal_reason}
                          </span>
                        )}
                        <span className="gh-run-cost t-mono">
                          cost USD {grouped(run.cost_usd)}
                        </span>
                      </li>
                    );
                  })}
                </ol>
              ))}

            {problem !== null && (
              <p className="gh-blocked t-mono" role="status">
                <Icon name="alert" size={12} />
                {problem}
              </p>
            )}

            {stillQueued && (
              <p className="gh-blocked t-mono" role="status">
                <Icon name="clock" size={12} />
                It is still queued. The rehearsal runs on the same worker as
                everything else in the estate, and when that worker is down a
                scenario waits rather than failing — nothing has been lost, and
                nothing further has been spent.
              </p>
            )}

            {/* ────────────────────────────────────────────────────────────────
                D7 §3.1's single exemption, spent here and nowhere else, and
                spent on words. A spinner would say "wait"; this says how long
                and what is happening. */}
            {running ? (
              <p className="gh-running" role="status">
                {/* An unlit lamp on purpose. §2.1 gives gold to "this needs
                    you" and "this is certified" and to nothing else, and
                    `data-breathing` is the beacon's — the product's one looping
                    animation, reserved for hands raised. A run in flight is
                    neither, so the sentence carries it. */}
                <span className="m-lamp" aria-hidden="true" />
                {RUN_WORDS}
              </p>
            ) : (
              <button className="m-btn" onClick={() => void runIt()}>
                <Icon name="forward" size={14} />
                {list.length === 0 ? "Price it and run it" : "Run it again"}
              </button>
            )}

            <p className="gh-note t-mono">
              Running prices it first and shows you the price. Over the day's
              budget it parks and resumes tomorrow rather than half-running.
            </p>
          </div>

          {/* ------------------------------------------------------ the grade */}
          <div className="gh-panel m-plate">
            <span className="t-eyebrow">HOW HONEST IS THIS</span>
            {grade === null ? (
              <p className="gh-blocked t-mono">
                There is no grade, because there is no run. A grade is computed
                by the engine from what a run actually had — there is no way for
                this screen to ask for one, and that is deliberate.
              </p>
            ) : (
              <div className="m-well gh-grade-well" data-deep>
                <GradeSeal grade={grade} />
              </div>
            )}
          </div>

          {/* -------------------------------------------------- the promotion */}
          <div className="gh-panel m-plate">
            <header className="gh-block-head">
              <span className="t-eyebrow">PROMOTION</span>
              <span className="t-mono gh-block-note">it climbs; it never skips</span>
            </header>

            <ol className="gh-chain">
              {PROMOTION_CHAIN.map((step) => (
                <li
                  className="gh-link"
                  key={step.key}
                  data-certified={step.certified || undefined}
                >
                  <span className="gh-link-mark" aria-hidden="true" />
                  <span className="gh-link-text">
                    <span className="gh-link-label">
                      {step.label}
                      {step.certified && <Icon name="key" size={11} className="gh-link-key" />}
                    </span>
                    <span className="gh-link-what">{step.what}</span>
                  </span>
                </li>
              ))}
            </ol>

            {/* §7.4 — the gap, rendered. No step here is drawn as reached: no
                endpoint reports where a scenario sits on this chain, and a lit
                step would be this screen's guess about the estate's own
                process. */}
            <p className="gh-blocked t-mono">
              Nothing here says which of these a scenario has reached — no
              endpoint reports it, so no step is lit. Promotion itself is taken
              from the colleague it would change: it amends a charter, and it
              needs the colleague and the field, which this room does not hold.
            </p>

            <p className="gh-note t-mono">
              Promotion reuses the estate's own gates — the same HITL
              checkpoint, the same board build, the same canary. Nothing here is
              a shortcut past them.
            </p>
          </div>
        </section>
      </div>
    </section>
  );
}

/** A stable empty collection — a fresh `[]` per render is a new identity for no
 *  change on screen. */
const NO_RUNS: readonly TwinRunView[] = [];

/**
 * The promotion chain, in order. A scenario climbs it; it never skips.
 *
 * A statement about the **platform's route**, not about any scenario — which is
 * why it is a constant rather than a binding, and why no step is drawn as
 * reached. The two gold links are the certified ones: approval and general
 * release both ask for a passkey. Everything else is warm-white, because a step
 * that happens automatically is not asking anything of you.
 */
const PROMOTION_CHAIN = [
  { key: "diffed", label: "Diff", what: "What would change, listed.", certified: false },
  { key: "approved", label: "Your approval", what: "A certified act. Asks for your passkey.", certified: true },
  { key: "board-built", label: "Board build", what: "The Meta-Agent board assembles it.", certified: false },
  { key: "canary", label: "Canary", what: "Runs beside the real on a slice, watched.", certified: false },
  { key: "ga", label: "General", what: "A certified act. The estate adopts it.", certified: true },
] as const;

/** The run's headline figure, with the word for what it counts. The first
 *  metric the run actually carries — never a key it does not have. */
function headlineOf(run: TwinRunView): string | null {
  for (const key of HEADLINE) {
    const value = metricNumber(run.metrics, key);
    if (value !== null) return grouped(value);
  }
  return null;
}

/** The room's structures, one per metric the run reports. An empty list means
 *  no room is drawn at all — see `Pane`. */
function roomFor(run: TwinRunView, side: "real" | "twin"): RoomItem[] {
  const items: RoomItem[] = [];
  const signals = metricNumber(run.metrics, "signals_replayed");
  if (signals !== null) {
    items.push({
      key: `${side}-signals`,
      kind: "fixture",
      variant: 0,
      heading: "SIGNALS",
      detail: String(signals),
    });
  }
  const calls = metricNumber(run.metrics, "simulated_calls");
  if (calls !== null) {
    items.push({
      key: `${side}-calls`,
      kind: "fixture",
      variant: 2,
      heading: "CALLS",
      detail: String(calls),
    });
  }
  const executed = metricNumber(run.metrics, "runs_executed");
  if (executed !== null) {
    /* The room gets a short flat label: a long one runs into the next
       structure. The full word is in the pane label, where there is room. */
    items.push({
      key: `${side}-runs`,
      kind: "workplace",
      variant: 0,
      heading: "runs",
      detail: String(executed),
    });
  }
  return items;
}

/**
 * The pending state: the Glasshouse's own structure, standing, with the words
 * not yet in it. The run's loading state is the exemption; **the first paint is
 * not**, so this is a scaffold like every other room's.
 *
 * The plates are drawn first and the bars go inside them — `vh-skeleton`'s
 * ground is a 6/255 delta on the raw canvas.
 */
function GlasshouseScaffold() {
  return (
    <section className="gh">
      <Scaffold label="The Glasshouse">
        <div className="gh-panes">
          <div className="gh-pane m-plate" data-sunken>
            <Bar width="xs" />
            <Bar width="sm" tall />
            <Lines n={2} />
          </div>
          <div className="gh-ribbon" />
          <div className="gh-pane m-plate" data-sunken>
            <Bar width="xs" />
            <Bar width="sm" tall />
            <Lines n={2} />
          </div>
        </div>
        <div className="gh-lower">
          <div className="m-plate gh-ghost-block">
            <Bar width="sm" />
            <Lines n={3} />
          </div>
          <div className="m-plate gh-ghost-block">
            <Bar width="xs" />
            <Lines n={4} />
          </div>
        </div>
      </Scaffold>
    </section>
  );
}

function Pane({
  side,
  eyebrow,
  figure,
  label,
  items,
  absentNote,
}: {
  side: "real" | "twin";
  eyebrow: string;
  figure: string | null;
  label: string;
  items: RoomItem[];
  absentNote?: string;
}) {
  const drained = side === "twin";

  return (
    <section className="gh-pane m-plate" data-side={side} data-sunken>
      <header className="gh-pane-head">
        <span className="t-eyebrow">{eyebrow}</span>
        {figure === null ? (
          <span className="gh-pane-absent t-mono">no reading</span>
        ) : (
          <span className="gh-pane-figure">{figure}</span>
        )}
        {label !== "" && <span className="t-mono gh-pane-label">{label}</span>}
      </header>

      {/* No room at all rather than an empty one: `Room` sizes its floor from
          the structures standing on it, so a room with nothing in it has no
          extent to draw. An absence gets the sentence instead. */}
      {items.length > 0 && (
        <div className="gh-pane-stage">
          <Room items={items} drained={drained} />
        </div>
      )}

      {items.length > 0 && (
        <dl className="gh-pane-legend">
          {items.map((item) => (
            <div className="gh-legend-row" key={item.key}>
              <dt className="t-eyebrow">{item.heading}</dt>
              <dd className="t-mono">
                {item.detail} ·{" "}
                {METRIC_WORD[
                  item.key.endsWith("signals")
                    ? "signals_replayed"
                    : item.key.endsWith("calls")
                      ? "simulated_calls"
                      : "runs_executed"
                ]}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {absentNote !== undefined && <p className="gh-pane-note t-mono">{absentNote}</p>}
    </section>
  );
}
