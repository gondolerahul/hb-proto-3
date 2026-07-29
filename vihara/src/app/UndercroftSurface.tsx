/**
 * The Undercroft (DRIVER D10, D6 §15) — depth 3, mono, operator density
 * regardless of the learned value (art bible §6): everything the
 * platform already exposes, in one place, plus the one Vihara-specific
 * addition — the **manifest inspector**, which is what makes the rest of
 * the product debuggable: without it, "why did she show me that" has no
 * answer anywhere.
 *
 * Two panels the wireframe names have no tenant read endpoint yet
 * (consent/DNC registry, feature flags) — they render as honest absence
 * lines, not empty registers.
 */
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { emitEcho, readManifestLog } from "../api/genui";
import { fetchExecutions, fetchTrace, type RunSummary } from "../api/entities";
import { fetchDefs } from "../api/tenant";

export interface SignalRow {
  id: string;
  type?: string;
  status?: string;
  created_at?: string | null;
  [key: string]: unknown;
}

export async function fetchSignals(): Promise<SignalRow[]> {
  return (await api.get<SignalRow[]>("/ai/signals", { params: { limit: 100 } }))
    .data;
}

export async function fetchTriggers(): Promise<Record<string, unknown>[]> {
  return (await api.get<Record<string, unknown>[]>("/ai/signals/triggers")).data;
}

export async function fetchEnvelope(): Promise<Record<string, unknown>> {
  return (await api.get<Record<string, unknown>>("/ai/loop/envelope")).data;
}

export async function fetchRoutingDecisions(): Promise<
  Record<string, unknown>[]
> {
  const response = await api.get<
    Record<string, unknown>[] | { decisions?: Record<string, unknown>[] }
  >("/ai/intelligence/routing-decisions");
  const data = response.data;
  if (Array.isArray(data)) return data;
  return data.decisions ?? [];
}

export interface UndercroftLoaders {
  signals: typeof fetchSignals;
  triggers: typeof fetchTriggers;
  envelope: typeof fetchEnvelope;
  executions: typeof fetchExecutions;
  trace: typeof fetchTrace;
  defs: typeof fetchDefs;
  routing: typeof fetchRoutingDecisions;
  manifestLog: typeof readManifestLog;
  echo: typeof emitEcho;
}

const REAL: UndercroftLoaders = {
  signals: fetchSignals,
  triggers: fetchTriggers,
  envelope: fetchEnvelope,
  executions: fetchExecutions,
  trace: fetchTrace,
  defs: fetchDefs,
  routing: fetchRoutingDecisions,
  manifestLog: readManifestLog,
  echo: emitEcho,
};

const PANELS = [
  "signals",
  "triggers",
  "envelope",
  "runs",
  "schema",
  "routing",
  "manifests",
] as const;

type Panel = (typeof PANELS)[number];

function Mono({ value }: { value: unknown }): JSX.Element {
  return <pre className="vh-trace">{JSON.stringify(value, null, 2)}</pre>;
}

export function UndercroftSurface({
  loaders = REAL,
  now = () => new Date(),
}: {
  loaders?: UndercroftLoaders;
  now?: () => Date;
}): JSX.Element {
  const [panel, setPanel] = useState<Panel>("signals");
  const [data, setData] = useState<unknown>(null);
  const [trace, setTrace] = useState<unknown>(null);

  useEffect(() => {
    setData(null);
    setTrace(null);
    const load: Record<Panel, () => Promise<unknown>> = {
      signals: loaders.signals,
      triggers: loaders.triggers,
      envelope: loaders.envelope,
      runs: loaders.executions,
      schema: loaders.defs,
      routing: loaders.routing,
      manifests: async () => loaders.manifestLog(),
    };
    void load[panel]()
      .then(setData)
      .catch(() => setData({ error: "this register could not be read" }));
    void loaders.echo({
      sentence: `drilled into the ${panel} register`,
      action_ref: { kind: "undercroft.drill", surface_id: "undercroft" },
    });
  }, [panel, loaders]);

  return (
    <div className="vh-undercroft" data-part="undercroft" data-density="operator">
      <nav className="vh-undercroft-nav" aria-label="registers">
        {PANELS.map((name) => (
          <button
            key={name}
            type="button"
            className="vh-quiet-link"
            disabled={name === panel}
            onClick={() => setPanel(name)}
          >
            {name}
          </button>
        ))}
      </nav>

      {panel === "runs" && Array.isArray(data) ? (
        <div>
          <table className="vh-register" data-part="runs-register">
            <tbody>
              {(data as RunSummary[]).slice(0, 30).map((run) => (
                <tr key={run.id}>
                  <td className="vh-mono">{run.id.slice(0, 8)}</td>
                  <td>{run.status}</td>
                  <td className="vh-mono">{run.created_at.slice(0, 19)}</td>
                  <td>
                    <button
                      type="button"
                      className="vh-quiet-link"
                      data-part="open-trace"
                      onClick={() => {
                        void loaders
                          .trace(run.id)
                          .then(setTrace)
                          .catch(() =>
                            setTrace({ error: "the trace could not be read" }),
                          );
                      }}
                    >
                      trace
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {trace !== null && <Mono value={trace} />}
        </div>
      ) : panel === "manifests" && Array.isArray(data) ? (
        <table className="vh-register" data-part="manifest-inspector">
          <thead>
            <tr>
              <th>surface</th>
              <th>verdict</th>
              <th>components</th>
              <th>cache age</th>
              <th>ttl</th>
            </tr>
          </thead>
          <tbody>
            {(data as ReturnType<typeof readManifestLog>).map((entry, index) => (
              <tr key={`${entry.surface}-${index}`}>
                <td className="vh-mono">
                  {entry.surface} · {entry.renderer}/{entry.density}
                </td>
                <td data-part="manifest-verdict">{entry.verdict}</td>
                <td className="vh-mono">{entry.component_count ?? "—"}</td>
                <td className="vh-mono">
                  {Math.max(
                    0,
                    Math.round(
                      (now().getTime() - new Date(entry.fetched_at).getTime()) /
                        1000,
                    ),
                  )}
                  s
                </td>
                <td className="vh-mono">{entry.ttl_seconds ?? "—"}s</td>
              </tr>
            ))}
            {(data as unknown[]).length === 0 && (
              <tr>
                <td colSpan={5}>
                  <p className="vh-quiet">
                    No manifest has been asked for this session.
                  </p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      ) : data === null ? (
        <p className="vh-quiet">reading…</p>
      ) : (
        <Mono value={data} />
      )}

      <footer className="vh-quiet" data-part="undercroft-absences">
        consent/DNC and tenant-visible flags have no tenant read endpoint
        yet — absent here rather than drawn empty.
      </footer>
    </div>
  );
}
