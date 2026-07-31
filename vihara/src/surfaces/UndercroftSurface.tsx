import { useState, type ReactNode } from "react";

import { Icon } from "../components/Icon";
import { fetchExecutions, type RunSummary } from "../api/entities";
import {
  fetchServedRegistry,
  readManifestLog,
  type ManifestLogEntry,
  type ServedRegistry,
} from "../api/genui";
import { fetchDefs, type EntityDef } from "../api/tenant";
import {
  fetchConsent,
  fetchEnvelopes,
  fetchFeatureFlags,
  fetchRoutingDecisions,
  fetchSignals,
  fetchTriggers,
  flagState,
  type BudgetEnvelopeOut,
  type ConsentView,
  type FeatureFlagView,
  type RoutingDecisionOut,
  type SignalOut,
  type TriggerRegistration,
} from "../api/undercroft";
import { Empty, Failed, Lines, Scaffold, useResource, type Resource } from "../lifecycle";
import "./undercroft.css";

/**
 * The Undercroft · depth 3 · S, dense (D6 §15). Wired in R-4 part W.
 *
 * The engine room, and the one surface in the product whose whole job is to be
 * checkable. **Mono throughout and pinned to operator density regardless of the
 * learned value** (art bible §6) — depth 3's audience is operators, and
 * softening it for a novice would only hide the thing they were sent here to
 * read.
 *
 * ## The four wrong source strings, and why they mattered here more
 *
 * Every bay prints the endpoint behind it, and the fallback copy asserted in
 * prose that the named endpoint "answers today". Three of the fixture's strings
 * were wrong and a fourth named a door that did not exist, which made this the
 * one surface where a stale string is a false statement rather than a stale
 * label. Each was checked against `src/api/openapi.json` rather than against the
 * fixture:
 *
 * | Bay | The fixture said | What answers |
 * |---|---|---|
 * | Schema browser | `GET /ai/tenant-schema/defs` | `GET /ai/tenant/defs` |
 * | Routing | `GET /ai/intelligence/routing` | `GET /ai/intelligence/routing-decisions` |
 * | Feature flags | `GET /ai/flags` | `GET /ai/admin/feature_flags/me` |
 * | Consent & DNC | `GET /ai/consent` | `GET /ai/consent` — which **did not exist** until D8's E1 built it this increment |
 *
 * The flags path is worth a sentence: it lives under `/ai/admin` and it is
 * **not** admin-only — it answers for the calling session and is what
 * `useFeatureFlag(key)` reads. The prefix is where the router was mounted, not
 * a statement about who may call it.
 *
 * ## Three decisions
 *
 *  - **The manifest inspector is first, and it is the point.** Everything else
 *    here is a view onto a subsystem that already had one; without the
 *    inspector, *"why did she show me that"* has no answer anywhere in the
 *    system. It is also the one bay with no endpoint behind it: the log is
 *    `readManifestLog()`, in memory, this session only, and the source line says
 *    so rather than naming `GET /ai/genui/manifest` — which serves a manifest
 *    and has never served a history of them.
 *  - **A bay counts what it loaded and nothing else.** The rail used to carry a
 *    figure against every bay. Nine counts for one loaded bay means eight
 *    invented numbers, so the count moved to the pane head where it is a fact
 *    about rows on screen (§7.1). Where the server caps a read, the cap is
 *    printed beside the count — a short list must not be read as "that is all
 *    there is".
 *  - **The routing bay shows no cost, and says which model and why instead.**
 *    `RoutingDecision` stores no cost at all; cost attribution lives against the
 *    run, which is why the traces bay *can* print one and this one cannot. A
 *    per-decision rupee figure was the fixture's invention and there is nothing
 *    to derive it from — a join that does not exist is not a rounding error.
 */

type BayKey =
  | "manifest"
  | "signals"
  | "triggers"
  | "envelopes"
  | "traces"
  | "schema"
  | "routing"
  | "consent"
  | "flags";

interface Bay {
  key: BayKey;
  label: string;
  /** What this bay is for, in an operator's terms. */
  purpose: string;
  /** The door behind it, verified against `openapi.json`. */
  source: string;
}

/**
 * The bays, keyed rather than listed.
 *
 * A `find(...) ?? BAYS[0]!` would be the index assertion L1 exists to retire —
 * and while this particular collection is nine literals in this file rather
 * than a network response, the rule is that an open item is *derived* and never
 * asserted into. A record indexed by a closed union is total, so there is
 * nothing to assert.
 */
const BAYS: Record<BayKey, Bay> = {
  manifest: {
    key: "manifest",
    label: "Manifest inspector",
    purpose: "What she rendered, why, and what it resolved against",
    source: "in memory · every manifest this session fetched",
  },
  signals: { key: "signals", label: "Signals", purpose: "The bus, newest first", source: "GET /ai/signals" },
  triggers: { key: "triggers", label: "Trigger registry", purpose: "What fires what", source: "GET /ai/signals/triggers" },
  envelopes: { key: "envelopes", label: "Envelopes", purpose: "Budget, spend, holds, reserve", source: "GET /ai/loop/envelope" },
  traces: { key: "traces", label: "Run traces", purpose: "Every root run, newest first", source: "GET /ai/executions" },
  schema: { key: "schema", label: "Schema browser", purpose: "Entity defs and their versions", source: "GET /ai/tenant/defs" },
  routing: { key: "routing", label: "Routing", purpose: "Which model, and why", source: "GET /ai/intelligence/routing-decisions" },
  consent: { key: "consent", label: "Consent & DNC", purpose: "Who asked us to stop", source: "GET /ai/consent" },
  flags: { key: "flags", label: "Feature flags", purpose: "What is on, for whom", source: "GET /ai/admin/feature_flags/me" },
};

/** Rail order. The manifest inspector is first because it is the point — see
 *  the component docstring. */
const BAY_ORDER: BayKey[] = [
  "manifest",
  "signals",
  "triggers",
  "envelopes",
  "traces",
  "schema",
  "routing",
  "consent",
  "flags",
];

export function UndercroftSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const [bay, setBay] = useState<BayKey>("manifest");
  const active = BAYS[bay];

  return (
    <section className="uc">
      {/* --------------------------------------------------------------- rail */}
      <nav className="uc-rail m-well" aria-label="Undercroft bays">
        <div className="uc-rail-head">
          <span className="t-eyebrow">THE UNDERCROFT</span>
          <span className="uc-rail-note">depth 3 · operator, always</span>
        </div>
        <ul className="uc-bays">
          {BAY_ORDER.map((key) => BAYS[key]).map((b) => (
            <li key={b.key} data-bay={b.key}>
              {/* No count. One bay is loaded at a time, so a figure against the
                  other eight would be eight numbers nobody measured. */}
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

        {/* `key` remounts the pane on every bay change, which is the only
            honest way to read a different thing: `useResource` captures its
            reader once, on purpose. */}
        <div className="uc-body" key={bay}>
          {bay === "manifest" && <ManifestBay />}
          {bay === "signals" && <SignalsBay />}
          {bay === "triggers" && <TriggersBay />}
          {bay === "envelopes" && <EnvelopesBay />}
          {bay === "traces" && <TracesBay />}
          {bay === "schema" && <SchemaBay />}
          {bay === "routing" && <RoutingBay />}
          {bay === "consent" && <ConsentBay />}
          {bay === "flags" && <FlagsBay />}
        </div>
      </div>
    </section>
  );
}

/* ========================================================================== */
/*  ONE BAY'S THREE STATES                                                    */
/* ========================================================================== */

/**
 * Pending, failed and empty for a bay, once rather than nine times.
 *
 * Empty is a designed state here and not a blank table, because an operator who
 * opens the routing bay and finds nothing has learnt something — *this estate
 * has never routed anything* — and a header over no rows says only that
 * something went wrong.
 */
function BayBody<T>({
  label,
  resource,
  isEmpty,
  emptyTitle,
  emptyBody,
  children,
}: {
  label: string;
  resource: Resource<T>;
  isEmpty: (value: T) => boolean;
  emptyTitle: string;
  emptyBody: string;
  children: (value: T) => ReactNode;
}) {
  if (resource.phase === "pending") return <BayScaffold label={label} />;

  if (resource.phase === "failed") {
    return (
      <Failed
        what={`the ${label.toLowerCase()}`}
        reason={resource.reason}
        onRetry={resource.retry}
      />
    );
  }

  if (isEmpty(resource.value)) {
    return <Empty icon="clock" title={emptyTitle} body={emptyBody} />;
  }

  return <>{children(resource.value)}</>;
}

/**
 * A bay's pending state: the well it will fill, standing, with bars in it.
 *
 * The well is drawn first and the bars go inside — `vh-skeleton`'s ground is a
 * ~6/255 delta on the raw canvas, so a bar on the page background is invisible.
 * No spinner: the Glasshouse is the only surface permitted a loading state and
 * this is not it.
 */
function BayScaffold({ label }: { label: string }) {
  return (
    <Scaffold label={`The ${label.toLowerCase()}`}>
      <div className="uc-stack">
        <div className="uc-table m-well" data-deep>
          <Lines n={7} />
        </div>
      </div>
    </Scaffold>
  );
}

/** The row count for what is on screen, with the server's cap beside it where
 *  there is one. A short list under a cap is not "that is all there is". */
function Counted({ n, note }: { n: number; note?: string }) {
  return (
    <p className="uc-count">
      {n} row{n === 1 ? "" : "s"}
      {note !== undefined && ` · ${note}`}
    </p>
  );
}

/** A wire timestamp, trimmed. Never through `toLocaleString`, which reshapes a
 *  figure with whatever ICU data the machine carries. */
function stamp(at: string | null): string {
  return at === null || at === "" ? "" : at.slice(0, 19).replace("T", " ");
}

/** An id, short enough for a dense table and long enough to grep for. */
function short(id: string): string {
  return id.slice(0, 8);
}

/* ========================================================= the manifest bay */

/**
 * The bay with no endpoint behind it.
 *
 * `readManifestLog()` is a capped, in-memory, newest-first list of every
 * manifest this session fetched — surface, renderer, density, the refusal
 * ladder's verdict and the reason where it refused. It is what makes the rest
 * of the product debuggable, and it is empty on a session that has not fetched
 * one, which is stated rather than filled with a plausible render.
 */
function ManifestBay() {
  const [showRegistry, setShowRegistry] = useState(false);
  const log = readManifestLog();

  return (
    <div className="uc-stack">
      {log.length === 0 ? (
        <Empty
          icon="record"
          title="No manifest has been fetched in this session."
          body="This log is held in memory and starts empty every time the app loads — there is no endpoint that serves a history of renders, and inventing one here would defeat the only bay whose job is to be checkable. Open a surface that asks for a manifest and it appears here."
        />
      ) : (
        <>
          <Counted n={log.length} note="in memory, this session, newest first" />
          <table className="uc-table m-well" data-deep>
            <caption className="vh-sr-only">
              Every manifest this session fetched, newest first
            </caption>
            <thead>
              <tr>
                <th scope="col">Surface</th>
                <th scope="col">Shape</th>
                <th scope="col">Verdict</th>
                <th scope="col" className="uc-num">
                  Components
                </th>
                <th scope="col" className="uc-num">
                  TTL
                </th>
                <th scope="col">Fetched</th>
              </tr>
            </thead>
            <tbody>
              {log.map((entry, i) => (
                <ManifestRow entry={entry} key={`${entry.fetched_at}:${i}`} />
              ))}
            </tbody>
          </table>
          <p className="uc-note">
            A component that was <strong>declined</strong> is usually the most
            useful line in a debugging session — it is the difference between
            what she asked for and what she was allowed.
          </p>
        </>
      )}

      <section className="uc-block">
        <button
          className="m-chip"
          onClick={() => setShowRegistry((v) => !v)}
          aria-expanded={showRegistry}
        >
          <Icon
            name="chevron"
            size={12}
            className="uc-caret"
            data-open={showRegistry || undefined}
          />
          the served component registry
        </button>
        {showRegistry && <ServedRegistryTable />}
      </section>
    </div>
  );
}

function ManifestRow({ entry }: { entry: ManifestLogEntry }) {
  const refused = entry.verdict !== "render";
  return (
    <tr data-flagged={refused || undefined}>
      <td>{entry.surface}</td>
      <td>
        {entry.renderer}:{entry.density}
      </td>
      <td>
        <span className="uc-state">
          <span className="m-lamp" data-negative={refused || undefined} />
          {entry.verdict}
        </span>
        {entry.reason !== undefined && (
          <span className="uc-why"> — {entry.reason}</span>
        )}
      </td>
      {/* An absent count renders as nothing. A rejected wire body never got as
          far as having components, and "0 components" would be a measurement
          nobody took. */}
      <td className="uc-num">{entry.component_count ?? ""}</td>
      <td className="uc-num">
        {entry.ttl_seconds === undefined ? "" : `${entry.ttl_seconds}s`}
      </td>
      <td>{stamp(entry.fetched_at)}</td>
    </tr>
  );
}

/**
 * The registry as the server serves it (`GET /ai/genui/registry`).
 *
 * `src/manifest/registry/*.json` is the authored source and the backend mirrors
 * it, so this is not how a manifest resolves — it is how a mirror drift becomes
 * visible in the product rather than only in CI.
 */
function ServedRegistryTable() {
  const registry = useResource<ServedRegistry>(fetchServedRegistry);

  return (
    <BayBody
      label="served registry"
      resource={registry}
      isEmpty={(view) => view.entries.length === 0}
      emptyTitle="The server is serving an empty registry."
      emptyBody="Nothing would render against this: every component a manifest can name has to be in the registry the server publishes, and it is publishing none. That is a deployment fact, not a quiet afternoon."
    >
      {(view) => (
        <div className="uc-stack vh-enter-fade">
          <Counted n={view.entries.length} note={`registry ${view.registry_version}`} />
          <table className="uc-table m-well" data-deep>
            <caption className="vh-sr-only">
              Components the server's registry publishes
            </caption>
            <thead>
              <tr>
                <th scope="col">Component</th>
                <th scope="col" className="uc-num">
                  Version
                </th>
                <th scope="col">Class</th>
              </tr>
            </thead>
            <tbody>
              {view.entries.map((entry) => (
                <tr key={`${entry.type}@${entry.version}`}>
                  <td>{entry.type}</td>
                  <td className="uc-num">{entry.version}</td>
                  <td>
                    <span className="uc-state">
                      <span
                        className="m-lamp"
                        data-lit={entry.class === "certified" || undefined}
                      />
                      {entry.class}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </BayBody>
  );
}

/* ================================================================== signals */

/** The bus's own state words, with a lamp each. Never colour alone (§4); a
 *  state this map has not met prints itself. */
const SIGNAL_LAMP: Record<string, "lit" | "positive" | "negative"> = {
  consumed: "positive",
  delivered: "positive",
  parked: "lit",
  dead: "negative",
  failed: "negative",
};

function SignalsBay() {
  const signals = useResource<SignalOut[]>(() => fetchSignals({ limit: 200 }));

  return (
    <BayBody
      label="signals"
      resource={signals}
      isEmpty={(rows) => rows.length === 0}
      emptyTitle="Nothing has been on the bus."
      emptyBody="Every inbound event, every internal proposal and every conflict passes through here, and this estate has raised none. A quiet bus on a new estate is expected; a quiet bus on a working one is the first thing to look at."
    >
      {(rows) => (
        <div className="uc-stack">
          <Counted n={rows.length} note="the server caps this read at 200 however many are asked for" />
          <table className="uc-table m-well" data-deep>
            <caption className="vh-sr-only">The signal bus, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Id</th>
                <th scope="col">Type</th>
                <th scope="col">Source</th>
                <th scope="col">State</th>
                <th scope="col" className="uc-num">
                  Attempts
                </th>
                <th scope="col">Raised</th>
                <th scope="col">Consumed</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((signal) => (
                <tr key={signal.id} data-flagged={signal.last_error !== null || undefined}>
                  <td>{short(signal.id)}</td>
                  <td>{signal.type}</td>
                  <td>{signal.source}</td>
                  <td>
                    <span className="uc-state">
                      <span
                        className="m-lamp"
                        data-lit={SIGNAL_LAMP[signal.status] === "lit" || undefined}
                        data-positive={SIGNAL_LAMP[signal.status] === "positive" || undefined}
                        data-negative={SIGNAL_LAMP[signal.status] === "negative" || undefined}
                      />
                      {signal.status}
                    </span>
                    {signal.last_error !== null && (
                      <span className="uc-why"> — {signal.last_error}</span>
                    )}
                  </td>
                  <td className="uc-num">{signal.attempts}</td>
                  <td>{stamp(signal.created_at)}</td>
                  {/* Empty until the dispatcher has claimed it. Never a time
                      that has not happened. */}
                  <td>{stamp(signal.consumed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </BayBody>
  );
}

/* ================================================================= triggers */

function TriggersBay() {
  const triggers = useResource<TriggerRegistration[]>(fetchTriggers);

  return (
    <BayBody
      label="trigger registry"
      resource={triggers}
      isEmpty={(rows) => rows.length === 0}
      emptyTitle="Nothing is registered to fire on anything."
      emptyBody="A trigger binds a signal pattern to a process, and no process on this estate is listening. Signals raised here reach the bus and stop there — which is worth knowing before you go looking for the run they should have started."
    >
      {(rows) => (
        <div className="uc-stack">
          <Counted n={rows.length} />
          <table className="uc-table m-well" data-deep>
            <caption className="vh-sr-only">What fires what</caption>
            <thead>
              <tr>
                <th scope="col">Pattern</th>
                <th scope="col">Process</th>
                <th scope="col" className="uc-num">
                  Priority
                </th>
                <th scope="col">State</th>
                <th scope="col">Registered</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((trigger) => (
                <tr key={trigger.id}>
                  <td>{trigger.type_pattern}</td>
                  <td>{short(trigger.process_entity_id)}</td>
                  <td className="uc-num">{trigger.priority}</td>
                  <td>
                    <span className="uc-state">
                      <span className="m-lamp" data-positive={trigger.enabled || undefined} />
                      {trigger.enabled ? "enabled" : "disabled"}
                    </span>
                  </td>
                  <td>{stamp(trigger.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </BayBody>
  );
}

/* ================================================================ envelopes */

function EnvelopesBay() {
  const envelopes = useResource<BudgetEnvelopeOut[]>(fetchEnvelopes);

  return (
    <BayBody
      label="envelopes"
      resource={envelopes}
      isEmpty={(rows) => rows.length === 0}
      emptyTitle="No colleague has a budget envelope."
      emptyBody="An envelope is what caps what one colleague may spend in a cycle, and none exists. Nothing here is over budget because nothing here has a budget — which is a different sentence from the reassuring one."
    >
      {(rows) => (
        <div className="uc-stack">
          <Counted n={rows.length} />
          <table className="uc-table m-well" data-deep>
            <caption className="vh-sr-only">Budget envelopes, spend and reserve</caption>
            <thead>
              <tr>
                <th scope="col">Entity</th>
                <th scope="col">Cycle</th>
                <th scope="col" className="uc-num">
                  Envelope
                </th>
                <th scope="col" className="uc-num">
                  Spent
                </th>
                <th scope="col" className="uc-num">
                  Reserved
                </th>
                <th scope="col" className="uc-num">
                  Used
                </th>
                <th scope="col">State</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((envelope) => (
                <tr key={envelope.id} data-flagged={envelope.capped || undefined}>
                  <td>{short(envelope.entity_id)}</td>
                  <td>{envelope.cycle}</td>
                  {/* The field names carry the denomination, so USD is the
                      platform's own word rather than this file's guess. */}
                  <td className="uc-num">USD {envelope.envelope_usd.toFixed(2)}</td>
                  <td className="uc-num">USD {envelope.spent_usd.toFixed(2)}</td>
                  <td className="uc-num">USD {envelope.reserved_usd.toFixed(2)}</td>
                  <td className="uc-num">{Math.round(envelope.utilization_pct)}%</td>
                  <td>
                    <span className="uc-state">
                      <span
                        className="m-lamp"
                        data-negative={envelope.capped || undefined}
                        data-lit={(!envelope.capped && envelope.downshift) || undefined}
                      />
                      {envelope.capped
                        ? "capped"
                        : envelope.downshift
                          ? "downshifting"
                          : "running"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="uc-note">
            <strong>Downshifting</strong> starts at the envelope&apos;s own
            threshold and means the router is choosing cheaper models, not that
            anything has stopped. <strong>Capped</strong> means the envelope is
            spent and work is refused until the cycle turns.
          </p>
        </div>
      )}
    </BayBody>
  );
}

/* =================================================================== traces */

function TracesBay() {
  const runs = useResource<RunSummary[]>(fetchExecutions);

  return (
    <BayBody
      label="run traces"
      resource={runs}
      isEmpty={(rows) => rows.length === 0}
      emptyTitle="Nothing has run on this estate."
      emptyBody="Every root execution this company has ever started would be listed here, and there are none. Not a filtered view of a busy estate — the whole table, and it is empty."
    >
      {(rows) => (
        <div className="uc-stack">
          <Counted
            n={rows.length}
            note="every root run this company has ever started; the endpoint takes no filter and no page"
          />
          <table className="uc-table m-well" data-deep>
            <caption className="vh-sr-only">Root executions, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Run</th>
                <th scope="col">Colleague</th>
                <th scope="col">State</th>
                <th scope="col" className="uc-num">
                  Cost
                </th>
                <th scope="col" className="uc-num">
                  Took
                </th>
                <th scope="col">Started</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 200).map((run) => (
                <tr key={run.id} data-flagged={run.error_message !== null || undefined}>
                  <td>{short(run.id)}</td>
                  <td>{short(run.entity_id)}</td>
                  <td>
                    <span className="uc-state">
                      <span
                        className="m-lamp"
                        data-negative={run.error_message !== null || undefined}
                        data-positive={
                          (run.error_message === null && run.completed_at !== null) || undefined
                        }
                      />
                      {run.status}
                    </span>
                    {run.error_message !== null && (
                      <span className="uc-why"> — {run.error_message}</span>
                    )}
                  </td>
                  {/* Cost lives here, against the run, which is exactly why the
                      routing bay cannot show one. */}
                  <td className="uc-num">USD {run.total_cost_usd.toFixed(4)}</td>
                  {/* Nothing timed renders as nothing, never as 0 ms. */}
                  <td className="uc-num">
                    {run.execution_time_ms === null ? "" : `${run.execution_time_ms} ms`}
                  </td>
                  <td>{stamp(run.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > 200 && (
            <p className="uc-note">
              Showing the newest 200 of {rows.length}. The endpoint has no limit
              and no filter, so the whole table came down the wire to get them —
              a paged, filterable execution read is the fix, not a bigger client.
            </p>
          )}
        </div>
      )}
    </BayBody>
  );
}

/* =================================================================== schema */

function SchemaBay() {
  const defs = useResource<EntityDef[]>(fetchDefs);

  return (
    <BayBody
      label="schema browser"
      resource={defs}
      isEmpty={(rows) => rows.length === 0}
      emptyTitle="This tenant has no entity definitions."
      emptyBody="A def is the shape of one kind of record — an invoice, a party, a contract. With none defined there is nothing for a colleague to read or write, and the halls upstairs will be empty for the same reason."
    >
      {(rows) => (
        <div className="uc-stack">
          <Counted n={rows.length} />
          <table className="uc-table m-well" data-deep>
            <caption className="vh-sr-only">Entity definitions and their versions</caption>
            <thead>
              <tr>
                <th scope="col">Object</th>
                <th scope="col">Module</th>
                <th scope="col">Owner</th>
                <th scope="col" className="uc-num">
                  Version
                </th>
                <th scope="col" className="uc-num">
                  Fields
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((def) => (
                <tr key={`${def.module}:${def.name}`}>
                  <td>{def.name}</td>
                  <td>{def.module}</td>
                  {/* An unowned def prints nothing rather than "none": the
                      column is a process code and there isn't one. */}
                  <td>{def.owner_process_code ?? ""}</td>
                  <td className="uc-num">{def.version}</td>
                  <td className="uc-num">{def.fields.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="uc-note">
            Which <strong>system</strong> masters each of these is declared on
            the def itself and this endpoint does not return it — which is why
            Bridges &amp; Gates leaves that column empty rather than guessing.
          </p>
        </div>
      )}
    </BayBody>
  );
}

/* ================================================================== routing */

function RoutingBay() {
  const decisions = useResource<RoutingDecisionOut[]>(() => fetchRoutingDecisions(200));

  return (
    <BayBody
      label="routing"
      resource={decisions}
      isEmpty={(rows) => rows.length === 0}
      emptyTitle="No model has been chosen yet."
      emptyBody="A routing decision is recorded every time a task is matched to a model. There are none, which means nothing has asked for one — not that everything defaulted."
    >
      {(rows) => (
        <div className="uc-stack">
          <Counted n={rows.length} note="the server clamps this read to 500" />
          <table className="uc-table m-well" data-deep>
            <caption className="vh-sr-only">Routing decisions, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Run</th>
                <th scope="col">Task</th>
                <th scope="col">Model</th>
                <th scope="col">Why</th>
                <th scope="col">When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((decision) => (
                <tr key={decision.id} data-flagged={decision.fallback_used || undefined}>
                  {/* A decision taken outside a run has no run to name. */}
                  <td>{decision.run_id === null ? "" : short(decision.run_id)}</td>
                  <td>{decision.task_type ?? ""}</td>
                  <td>
                    <span className="uc-state">
                      <span className="m-lamp" data-lit={decision.fallback_used || undefined} />
                      {decision.model_registry_id ?? ""}
                    </span>
                  </td>
                  <td className="uc-why">{decision.reason ?? ""}</td>
                  <td>{stamp(decision.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="uc-note">
            A lit lamp is a <strong>fallback</strong> — the first choice was not
            available and the router took the next one. It is not an error, and
            it is worth knowing about, which is why it is marked rather than
            hidden.
          </p>
          {/* The column that is not here, named rather than quietly dropped. */}
          <p className="uc-note">
            <strong>There is no cost column, and there cannot be one.</strong> A
            routing decision records which model and why; it stores no cost at
            all. Cost is attributed against the <em>run</em>, and the run traces
            bay prints it there. Deriving a per-decision figure would mean
            splitting a run&apos;s cost across its decisions by a rule nobody has
            written — an invented number in the one room that exists to be
            checked.
          </p>
        </div>
      )}
    </BayBody>
  );
}

/* ================================================================== consent */

function ConsentBay() {
  const consent = useResource<ConsentView>(() => fetchConsent(200));

  return (
    <BayBody
      label="consent and DNC"
      resource={consent}
      isEmpty={(view) => view.entries.length === 0 && view.channels.length === 0}
      emptyTitle="Nobody has asked this estate to stop."
      emptyBody="The registry holds a row the moment somebody opts in, opts out, unsubscribes or lands on a do-not-contact list, and it holds none. Every send is still checked against it before it leaves — an empty registry is a young estate, not a permissive one."
    >
      {(view) => (
        <div className="uc-stack">
          <Counted n={view.entries.length} note={`limit ${view.limit} · as of ${stamp(view.as_of)}`} />

          <div className="uc-grid">
            {[
              ["Do not contact", view.totals.dnc],
              ["Unsubscribed", view.totals.unsubscribed],
              ["Said yes", view.totals.granted],
              ["Said no", view.totals.denied],
            ].map(([label, value]) => (
              <div className="uc-cell m-well" key={String(label)}>
                <span className="t-eyebrow">{String(label)}</span>
                <span className="uc-cell-val">{value}</span>
              </div>
            ))}
          </div>

          <section className="uc-block">
            <h2 className="t-eyebrow">POSTURE, PER CHANNEL</h2>
            <table className="uc-table m-well" data-deep>
              <caption className="vh-sr-only">
                Each channel&apos;s posture in the registry&apos;s own words
              </caption>
              <thead>
                <tr>
                  <th scope="col">Channel</th>
                  <th scope="col">Posture</th>
                  <th scope="col">The registry&apos;s reason</th>
                </tr>
              </thead>
              <tbody>
                {view.channels.map((channel) => (
                  <tr key={channel.channel}>
                    <td>{channel.channel}</td>
                    <td>
                      <span className="uc-state">
                        <span
                          className="m-lamp"
                          data-positive={channel.posture === "open" || undefined}
                          data-negative={channel.posture === "closed" || undefined}
                        />
                        {channel.posture}
                      </span>
                    </td>
                    <td className="uc-why">{channel.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="uc-note">
              Posture is reported for <strong>marketing</strong> and{" "}
              <strong>transactional</strong> only. Recording is left out
              deliberately: nothing sets it yet, and publishing &ldquo;open&rdquo;
              for a purpose no tenant was ever asked about would be a claim the
              registry cannot support.
            </p>
          </section>

          <section className="uc-block">
            <h2 className="t-eyebrow">WHO ASKED US TO STOP</h2>
            <table className="uc-table m-well" data-deep>
              <caption className="vh-sr-only">
                Consent, do-not-contact and unsubscribe rows, newest first
              </caption>
              <thead>
                <tr>
                  <th scope="col">Kind</th>
                  <th scope="col">Channel</th>
                  <th scope="col">Counterparty</th>
                  <th scope="col">Purpose</th>
                  <th scope="col">Why</th>
                  <th scope="col">When</th>
                </tr>
              </thead>
              <tbody>
                {view.entries.map((entry, i) => (
                  <tr key={`${entry.kind}:${entry.channel}:${entry.identity}:${i}`}>
                    <td>{entry.kind}</td>
                    <td>{entry.channel}</td>
                    <td>{entry.identity}</td>
                    {/* A DNC row has no purpose and no status. The columns the
                        other two tables do not have stay empty rather than
                        being flattened into a plausible word. */}
                    <td>
                      {entry.purpose ?? ""}
                      {entry.status !== null && ` · ${entry.status}`}
                    </td>
                    <td className="uc-why">{entry.reason ?? ""}</td>
                    <td>{stamp(entry.at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      )}
    </BayBody>
  );
}

/* ==================================================================== flags */

function FlagsBay() {
  const flags = useResource<FeatureFlagView>(fetchFeatureFlags);

  return (
    <BayBody
      label="feature flags"
      resource={flags}
      isEmpty={(view) =>
        Object.keys(view.defaults).length === 0 &&
        Object.keys(view.overrides).length === 0 &&
        Object.keys(view.numeric_defaults).length === 0
      }
      emptyTitle="The flag registry is empty."
      emptyBody="Every switch this platform ships would be listed here with its default and whoever overrode it. Nothing is registered, so nothing is behind a flag — which is not the same as everything being on."
    >
      {(view) => {
        const keys = [
          ...new Set([...Object.keys(view.defaults), ...Object.keys(view.overrides)]),
        ].sort();
        const numeric = Object.entries(view.numeric_defaults).sort(([a], [b]) =>
          a.localeCompare(b),
        );

        return (
          <div className="uc-stack">
            <Counted n={keys.length} note="defaults, then whoever overrode them" />
            <table className="uc-table m-well" data-deep>
              <caption className="vh-sr-only">Feature flags and who set them</caption>
              <thead>
                <tr>
                  <th scope="col">Flag</th>
                  <th scope="col">State</th>
                  <th scope="col">Set by</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => {
                  const state = flagState(view, key);
                  return (
                    <tr key={key}>
                      <td>{key}</td>
                      <td>
                        {/* `null` is "the registry has never heard of this
                            key", which is a different answer from "off" and is
                            said in words rather than drawn as a dark lamp. */}
                        {state === null ? (
                          <span className="uc-why">not in the registry</span>
                        ) : (
                          <span className="uc-state">
                            <span className="m-lamp" data-positive={state.on || undefined} />
                            {state.on ? "on" : "off"}
                          </span>
                        )}
                      </td>
                      <td>{state === null ? "" : state.scope}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {numeric.length > 0 && (
              <section className="uc-block">
                <h2 className="t-eyebrow">NUMERIC DEFAULTS</h2>
                <div className="uc-grid">
                  {numeric.map(([key, value]) => (
                    <div className="uc-cell m-well" key={key}>
                      <span className="t-eyebrow">{key}</span>
                      <span className="uc-cell-val">{value}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            <p className="uc-note">
              An override is keyed by scope, so <code>company</code> and{" "}
              <code>global</code> are different statements and the last one wins.
              That is why this table names who set a flag rather than flattening
              it to a single yes or no.
            </p>
          </div>
        );
      }}
    </BayBody>
  );
}
