import { useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { Room, type RoomItem } from "../world/Room";
import { GradeSeal } from "./BoardroomSurface";
import { PROMOTION_CHAIN, SCENARIOS, TWIN_SPEND, type Lever } from "../fixtures/glasshouse";
import "./glasshouse.css";

/**
 * The Glasshouse · depth 2 · W+S, desaturated (D6 §12).
 *
 * Two panes, and the whole surface hangs on one property: **the twin is the real,
 * drained.** Not recoloured — the same room with the life taken out of it. A blue
 * twin would say "different place"; a drained twin says "not yet real".
 *
 * Three decisions a reader could not infer from the markup:
 *
 *  - **Draining is applied at the plane boundary, by the renderer** (`Room`'s
 *    `drained` prop), never chosen per element. That is what makes it unforgeable:
 *    a twin-derived component cannot be styled to look real. L6 asks the manifest
 *    layer to enforce that honesty; here the *material* enforces it too.
 *  - **Gold inside the twin is reserved for exactly two things** — the divergence
 *    ribbon and certified seals on the promotion chain. Everything else is silver.
 *    So the one thing your eye finds in a simulation is the thing that *differs
 *    from reality*, which is the only reason to be in there.
 *  - **A grade governs what may be displayed, not just what is labelled.** An
 *    `untested` scenario has no twin reading, so the divergence ribbon is absent
 *    and the pane says why. Rendering a zero there — or a dash — would put a
 *    number against a simulation that never ran.
 *
 * Cost is visible because twin spend is tenant-initiated (charter decision 6): a
 * cost the tenant chose to incur is a cost they are owed a number for.
 */
export function GlasshouseSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const [activeId, setActiveId] = useState(SCENARIOS[0]!.id);
  const [levers, setLevers] = useState<Record<string, number>>({});
  const scenario = SCENARIOS.find((s) => s.id === activeId) ?? SCENARIOS[0]!;

  const leverValue = (l: Lever) => levers[`${scenario.id}:${l.key}`] ?? l.twin;
  const touched = scenario.levers.some((l) => leverValue(l) !== l.twin);

  /** Both panes are the same room, so a difference between them is real. */
  const roomFor = (side: "real" | "twin"): RoomItem[] => [
    {
      key: `${side}-kpi`,
      kind: "fixture",
      variant: 0,
      heading: scenario.measure.label.split(" ")[0]!.toUpperCase(),
      detail:
        side === "real"
          ? `${scenario.measure.real}${scenario.measure.unit}`
          : scenario.measure.twin === null
            ? "no reading"
            : `${scenario.measure.twin}${scenario.measure.unit}`,
    },
    {
      key: `${side}-work`,
      kind: "fixture",
      variant: 2,
      heading: "Work",
      detail: side === "real" ? "live" : "replayed",
    },
    /* The room gets the lever's KEY, not its label: "cadence" fits on a floor,
       "chase cadence" runs into the next structure. The full label is in the
       lever panel, where there is room for a phrase. */
    ...scenario.levers.map((l, i) => ({
      key: `${side}-${l.key}`,
      kind: "workplace" as const,
      variant: i,
      heading: l.key,
      detail: `${side === "real" ? l.real : leverValue(l)}${l.unit}`,
    })),
  ];

  const divergence =
    scenario.measure.twin === null ? null : scenario.measure.twin - scenario.measure.real;

  return (
    <section className="gh">
      {/* ------------------------------------------------------------- header */}
      <header className="gh-head">
        <div className="gh-head-lead">
          <span className="t-eyebrow">THE GLASSHOUSE · SIMULATION</span>
          <h1 className="gh-title t-display">Try it here first</h1>
          <p className="t-narrative gh-lead">
            Nothing in this room can touch the real. Everything you see on the right
            is drained, and it stays drained until it is promoted.
          </p>
        </div>
        <div className="gh-spend m-well">
          <span className="t-eyebrow">THIS MONTH</span>
          <span className="gh-spend-figure t-mono">
            ₹{TWIN_SPEND.monthINR} · {TWIN_SPEND.runs} runs
          </span>
          <p className="gh-spend-note t-mono">{TWIN_SPEND.note}</p>
        </div>
      </header>

      {/* ============================================================ the panes */}
      <div className="gh-panes">
        <Pane
          side="real"
          eyebrow="REAL · LIVE"
          figure={`${scenario.measure.real}${scenario.measure.unit}`}
          label={scenario.measure.label}
          items={roomFor("real")}
        />

        {/* The divergence ribbon — sanctioned gold inside the twin, and the only
            thing here that is asking to be looked at. Absent when there is no
            twin reading, because a ribbon between one number and nothing is a
            ribbon that invents the second number. */}
        <div className="gh-ribbon" aria-hidden={divergence === null || undefined}>
          {divergence === null ? (
            <span className="gh-ribbon-absent t-mono">no reading to compare</span>
          ) : (
            <>
              <span className="gh-ribbon-line" />
              <span className="gh-ribbon-val">
                {divergence > 0 ? "+" : ""}
                {divergence}
                {scenario.measure.unit}
              </span>
              <span className="gh-ribbon-line" />
            </>
          )}
        </div>

        <Pane
          side="twin"
          eyebrow="TWIN · DRAINED"
          figure={
            scenario.measure.twin === null
              ? null
              : `${scenario.measure.twin}${scenario.measure.unit}`
          }
          label={scenario.measure.label}
          items={roomFor("twin")}
          absentNote={
            scenario.measure.twin === null
              ? "This has never been run, so there is no reading. I am not going to put a number here."
              : undefined
          }
        />
      </div>

      {/* ============================================================ the shelf */}
      <div className="gh-lower">
        <section className="gh-shelf" aria-label="The scenario shelf">
          <header className="gh-block-head">
            <span className="t-eyebrow">THE SHELF</span>
            <span className="t-mono gh-block-note">
              {SCENARIOS.length} scenarios · each graded before you bet
            </span>
          </header>
          <div className="gh-shelf-list">
            {SCENARIOS.map((s) => (
              <button
                key={s.id}
                className="gh-card m-plate"
                data-active={s.id === activeId || undefined}
                onClick={() => {
                  setActiveId(s.id);
                  onEcho(`opened scenario ${s.id}`);
                }}
              >
                <span className="gh-card-head">
                  <span className="t-mono gh-card-id">{s.id}</span>
                  <GradeSeal grade={s.grade} compact />
                </span>
                <span className="gh-card-label t-display">{s.label}</span>
                <span className="gh-card-q">{s.question}</span>
                {/* A null cost renders as nothing — never ₹0. */}
                {s.costINR !== null && (
                  <span className="t-mono gh-card-cost">cost ₹{s.costINR}</span>
                )}
              </button>
            ))}
          </div>
        </section>

        {/* ------------------------------------------------------- the controls */}
        <section className="gh-controls" aria-label="Levers and promotion">
          <div className="gh-panel m-plate">
            <header className="gh-block-head">
              <span className="t-eyebrow">LEVERS</span>
              {touched && (
                <button
                  className="m-chip"
                  onClick={() => {
                    setLevers((m) => {
                      const next = { ...m };
                      for (const l of scenario.levers) delete next[`${scenario.id}:${l.key}`];
                      return next;
                    });
                  }}
                >
                  <Icon name="undo" size={12} />
                  reset
                </button>
              )}
            </header>

            {scenario.levers.map((l) => (
              <label className="gh-lever" key={l.key}>
                <span className="gh-lever-top">
                  <span className="gh-lever-label t-mono">{l.label}</span>
                  <span className="gh-lever-vals t-mono">
                    <span className="gh-lever-real">
                      {l.real}
                      {l.unit}
                    </span>
                    <span className="gh-lever-arrow">→</span>
                    <span className="gh-lever-twin">
                      {leverValue(l)}
                      {l.unit}
                    </span>
                  </span>
                </span>
                <input
                  className="gh-slider"
                  type="range"
                  min={l.min}
                  max={l.max}
                  step={l.step}
                  value={leverValue(l)}
                  onChange={(e) =>
                    setLevers((m) => ({
                      ...m,
                      [`${scenario.id}:${l.key}`]: Number(e.target.value),
                    }))
                  }
                />
              </label>
            ))}

            {/* Moving a lever invalidates the reading. Saying so is the whole
                point of the honesty grades — a stale number beside a moved lever
                is the most convincing wrong number in the product. */}
            {touched && (
              <p className="gh-stale t-mono">
                <Icon name="alert" size={12} />
                You have moved a lever, so the reading above is from the previous
                run and no longer describes what you are looking at. Re-run to
                grade it.
              </p>
            )}

            <button
              className="m-btn"
              onClick={() => onEcho(`re-ran ${scenario.id} in the Glasshouse`)}
            >
              <Icon name="forward" size={14} />
              Run it {touched ? "again" : ""}
            </button>
          </div>

          {/* ------------------------------------------------------ the grade */}
          <div className="gh-panel m-plate">
            <span className="t-eyebrow">HOW HONEST IS THIS</span>
            <div className="m-well gh-grade-well" data-deep>
              <GradeSeal grade={scenario.grade} />
            </div>
          </div>

          {/* -------------------------------------------------- the promotion */}
          <div className="gh-panel m-plate">
            <header className="gh-block-head">
              <span className="t-eyebrow">PROMOTION</span>
              <span className="t-mono gh-block-note">it climbs; it never skips</span>
            </header>

            <ol className="gh-chain">
              {PROMOTION_CHAIN.map((step) => {
                const order = PROMOTION_CHAIN.findIndex((x) => x.key === scenario.promotion);
                const myIndex = PROMOTION_CHAIN.findIndex((x) => x.key === step.key);
                const reached = order >= myIndex && scenario.promotion !== "none";
                return (
                  <li
                    className="gh-link"
                    key={step.key}
                    data-reached={reached || undefined}
                    data-certified={step.certified || undefined}
                  >
                    <span className="gh-link-mark" aria-hidden="true" />
                    <span className="gh-link-text">
                      <span className="gh-link-label">
                        {step.label}
                        {step.certified && (
                          <Icon name="key" size={11} className="gh-link-key" />
                        )}
                      </span>
                      <span className="gh-link-what">{step.what}</span>
                    </span>
                  </li>
                );
              })}
            </ol>

            {scenario.grade.grade === "untested" ? (
              <p className="gh-blocked t-mono">
                An untested scenario cannot be promoted. There is nothing behind it
                to diff against, so the first step is to run it.
              </p>
            ) : (
              <button
                className="m-btn"
                data-rank="certified"
                onClick={() => onEcho(`promoted scenario ${scenario.id} to canary`)}
              >
                <Icon name="key" size={14} />
                Approve and promote
              </button>
            )}

            <p className="gh-note t-mono">
              Promotion reuses the estate's own gates — the same HITL checkpoint, the
              same board build, the same canary. Nothing here is a shortcut past
              them.
            </p>
          </div>
        </section>
      </div>
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
  const roomItems = useMemo(() => items, [items]);

  return (
    <section className="gh-pane m-plate" data-side={side} data-sunken>
      <header className="gh-pane-head">
        <span className="t-eyebrow">{eyebrow}</span>
        {figure === null ? (
          <span className="gh-pane-absent t-mono">no reading</span>
        ) : (
          <span className="gh-pane-figure">{figure}</span>
        )}
        <span className="t-mono gh-pane-label">{label}</span>
      </header>

      <div className="gh-pane-stage">
        <Room items={roomItems} drained={drained} />
      </div>

      {absentNote && <p className="gh-pane-note t-mono">{absentNote}</p>}
    </section>
  );
}
