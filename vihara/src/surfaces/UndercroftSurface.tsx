import { useState } from "react";
import { Icon } from "../components/Icon";
import {
  BAYS,
  FLAGS,
  MANIFEST,
  ROUTING,
  SIGNALS,
  type BayKey,
} from "../fixtures/undercroft";
import "./undercroft.css";

/**
 * The Undercroft · depth 3 · S, dense (D6 §15).
 *
 * The engine room. **Mono throughout and pinned to operator density regardless of
 * the learned value** (art bible §6) — depth 3's audience is operators, and
 * softening it for a novice would only hide the thing they were sent here to read.
 *
 * Three decisions:
 *
 *  - **The manifest inspector is first, and it is the point.** Everything else
 *    here is a view onto a subsystem that already had one. The inspector is
 *    Vihara-specific and it is what makes the rest of the product debuggable:
 *    without it, *"why did she show me that"* has no answer anywhere in the
 *    system. It carries the four things you need to reproduce a render — the
 *    manifest as served, its `intent_shape`, its cache age, and the registry
 *    versions it resolved against — plus the refusals, because a component that
 *    was *declined* is the most useful line in a debugging session.
 *  - **This surface should feel like an instrument, not a dashboard.** Dense and
 *    cheap are different things. Wells, hairlines, corner ticks, tabular figures
 *    and a mono type stack throughout; no cards, no rounded panels of prose, no
 *    decoration. It is allowed to look technical and is not allowed to look
 *    unfinished.
 *  - **Every bay names its own endpoint.** An operator reading a number here will
 *    eventually need to ask the API the same question, and a surface that shows
 *    data without saying where it came from turns them into a detective.
 */
export function UndercroftSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const [bay, setBay] = useState<BayKey>("manifest");
  const active = BAYS.find((b) => b.key === bay)!;

  return (
    <section className="uc">
      {/* --------------------------------------------------------------- rail */}
      <nav className="uc-rail m-well" aria-label="Undercroft bays">
        <div className="uc-rail-head">
          <span className="t-eyebrow">THE UNDERCROFT</span>
          <span className="uc-rail-note">depth 3 · operator, always</span>
        </div>
        <ul className="uc-bays">
          {BAYS.map((b) => (
            <li key={b.key}>
              <button
                className="uc-bay"
                data-active={bay === b.key || undefined}
                data-primary={b.key === "manifest" || undefined}
                onClick={() => {
                  setBay(b.key);
                  onEcho(`opened the ${b.label.toLowerCase()}`);
                }}
                aria-current={bay === b.key ? "true" : undefined}
              >
                <span className="uc-bay-label">{b.label}</span>
                {/* A null count renders as nothing — the manifest inspector has no
                    count, and "0" would be a lie about an inspector. */}
                {b.count !== null && (
                  <span className="uc-bay-count">{b.count.toLocaleString("en-IN")}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* --------------------------------------------------------------- pane */}
      <div className="uc-pane">
        <header className="uc-pane-head">
          <div>
            <h1 className="uc-pane-title">{active.label}</h1>
            <p className="uc-pane-purpose">{active.purpose}</p>
          </div>
          {/* Where the data came from. Otherwise an operator has to guess. */}
          <code className="uc-source">{active.source}</code>
        </header>

        <div className="uc-body">
          {bay === "manifest" && <ManifestBay />}
          {bay === "signals" && <SignalsBay />}
          {bay === "routing" && <RoutingBay />}
          {bay === "flags" && <FlagsBay />}
          {!["manifest", "signals", "routing", "flags"].includes(bay) && (
            <Unbuilt label={active.label} source={active.source} />
          )}
        </div>
      </div>
    </section>
  );
}

/* ======================================================= the manifest inspector */

function ManifestBay() {
  const [showJson, setShowJson] = useState(false);

  return (
    <div className="uc-stack">
      <div className="uc-grid">
        {[
          ["Surface", MANIFEST.surface],
          ["Intent shape", MANIFEST.intentShape],
          ["Served at", MANIFEST.servedAt],
          ["Cache age", `${MANIFEST.cacheAgeSeconds}s`],
          ["Honesty grade", MANIFEST.honestyGrade],
        ].map(([k, v]) => (
          <div className="uc-cell m-well" key={k}>
            <span className="t-eyebrow">{k}</span>
            <span className="uc-cell-val">{v}</span>
          </div>
        ))}
      </div>

      <section className="uc-block">
        <h2 className="t-eyebrow">CACHE KEY</h2>
        <code className="uc-key m-well" data-deep>
          {MANIFEST.cacheKey}
        </code>
        <p className="uc-note">
          Keyed on <strong>shape</strong>, never on tenant. A tenant-dependent key
          would leak one tenant’s manifest into another’s render, so the absence of
          a tenant id in that string is a security property and not an omission.
        </p>
      </section>

      <section className="uc-block">
        <h2 className="t-eyebrow">RESOLVED AGAINST</h2>
        <table className="uc-table m-well" data-deep>
          <caption className="vh-sr-only">Registry components this manifest resolved against</caption>
          <thead>
            <tr>
              <th scope="col">Component</th>
              <th scope="col">Version</th>
              <th scope="col">Set</th>
            </tr>
          </thead>
          <tbody>
            {MANIFEST.registry.map((r) => (
              <tr key={r.component}>
                <td>{r.component}</td>
                <td className="uc-num">{r.version}</td>
                <td>
                  <span className="uc-state">
                    <span className="m-lamp" data-lit={r.certified || undefined} />
                    {r.certified ? "certified" : "open"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="uc-block">
        <h2 className="t-eyebrow">REFUSALS</h2>
        {MANIFEST.refusals.length === 0 ? (
          <p className="uc-note">Nothing was refused rendering this manifest.</p>
        ) : (
          <ul className="uc-refusals m-well">
            {MANIFEST.refusals.map((r) => (
              <li className="uc-refusal" key={r.what}>
                <span className="m-lamp" data-negative />
                <span className="uc-refusal-at">{r.at}</span>
                <span className="uc-refusal-what">{r.what}</span>
                <span className="uc-refusal-why">{r.why}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="uc-note">
          A component that was <strong>declined</strong> is usually the most useful
          line in a debugging session — it is the difference between what she asked
          for and what she was allowed.
        </p>
      </section>

      <section className="uc-block">
        <button
          className="m-chip"
          onClick={() => setShowJson((v) => !v)}
          aria-expanded={showJson}
        >
          <Icon name="chevron" size={12} className="uc-caret" data-open={showJson || undefined} />
          the manifest as served
        </button>
        {showJson && (
          <pre className="uc-json m-well vh-enter-fade" data-deep>
            {MANIFEST.json}
          </pre>
        )}
      </section>
    </div>
  );
}

/* ================================================================== signals */

const SIGNAL_STATE: Record<string, { word: string; lamp: "lit" | "positive" | "negative" | "plain" }> = {
  delivered: { word: "delivered", lamp: "positive" },
  parked: { word: "parked", lamp: "lit" },
  dead: { word: "dead", lamp: "negative" },
  "in-flight": { word: "in flight", lamp: "plain" },
};

function SignalsBay() {
  return (
    <table className="uc-table m-well" data-deep>
      <caption className="vh-sr-only">The signal bus, most recent first</caption>
      <thead>
        <tr>
          <th scope="col">Id</th>
          <th scope="col">Kind</th>
          <th scope="col">At</th>
          <th scope="col">State</th>
          <th scope="col" className="uc-num">
            Attempts
          </th>
          <th scope="col" className="uc-num">
            Latency
          </th>
        </tr>
      </thead>
      <tbody>
        {SIGNALS.map((s) => {
          const st = SIGNAL_STATE[s.state]!;
          return (
            <tr key={s.id}>
              <td>{s.id}</td>
              <td>{s.kind}</td>
              <td>{s.at}</td>
              <td>
                <span className="uc-state">
                  <span
                    className="m-lamp"
                    data-lit={st.lamp === "lit" || undefined}
                    data-positive={st.lamp === "positive" || undefined}
                    data-negative={st.lamp === "negative" || undefined}
                  />
                  {st.word}
                </span>
              </td>
              <td className="uc-num">{s.attempts}</td>
              {/* null until the dispatcher has claimed it — renders as nothing,
                  never as 0ms, which would claim an impossible latency. */}
              <td className="uc-num">{s.latencyMs === null ? "" : `${s.latencyMs} ms`}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/* ================================================================== routing */

function RoutingBay() {
  return (
    <div className="uc-stack">
      <table className="uc-table m-well" data-deep>
        <caption className="vh-sr-only">Routing decisions, most recent first</caption>
        <thead>
          <tr>
            <th scope="col">Run</th>
            <th scope="col">Task</th>
            <th scope="col">Model</th>
            <th scope="col">Why</th>
            <th scope="col" className="uc-num">
              Cost
            </th>
          </tr>
        </thead>
        <tbody>
          {ROUTING.map((r) => (
            <tr key={r.runId} data-flagged={r.downshifted || undefined}>
              <td>{r.runId}</td>
              <td>{r.task}</td>
              <td>
                <span className="uc-state">
                  <span className="m-lamp" data-lit={r.downshifted || undefined} />
                  {r.model}
                </span>
              </td>
              <td className="uc-why">{r.why}</td>
              <td className="uc-num">₹{r.costINR.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="uc-note">
        A lit lamp is a <strong>downshift</strong> — the router chose a cheaper model
        than the task's band because the wallet was thin. It is not an error, and it
        is worth knowing about, which is why it is marked rather than hidden.
      </p>
    </div>
  );
}

/* ==================================================================== flags */

function FlagsBay() {
  return (
    <table className="uc-table m-well" data-deep>
      <caption className="vh-sr-only">Feature flags and their scope</caption>
      <thead>
        <tr>
          <th scope="col">Flag</th>
          <th scope="col">State</th>
          <th scope="col">Scope</th>
        </tr>
      </thead>
      <tbody>
        {FLAGS.map((f) => (
          <tr key={f.key}>
            <td>{f.key}</td>
            <td>
              <span className="uc-state">
                <span className="m-lamp" data-positive={f.on || undefined} />
                {f.on ? "on" : "off"}
              </span>
            </td>
            <td>{f.scope}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ================================================================= unbuilt
   The remaining bays are views onto endpoints that already ship. Rendering a
   plausible table for them would be inventing data; naming the endpoint and
   saying the view is not built is the honest thing and takes one line. */

function Unbuilt({ label, source }: { label: string; source: string }) {
  return (
    <div className="uc-unbuilt m-well">
      <span className="m-lamp" />
      <div>
        <p className="uc-unbuilt-line">
          The {label.toLowerCase()} view is not drawn yet.
        </p>
        <p className="uc-note">
          The data ships — <code>{source}</code> answers today. What is missing is
          this bay's table, not the endpoint behind it. Drawing a plausible one here
          would be inventing rows, and the Undercroft is the last surface in the
          product that should do that.
        </p>
      </div>
    </div>
  );
}
