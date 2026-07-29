/**
 * The district room's working sheet (DRIVER D4, D6 §5) — the furnishing
 * App.tsx promised itself at SUB time ("its sheet, until DRIVER furnishes
 * it"). L9's rule holds: identical data to the W room, vertical stack, no
 * camera — the plinth is a KPI row, the treasury a bar, the weather its
 * sentence, colleagues a table, live runs a register.
 *
 * The protected reserve is the ONE gold thing on the treasury bar (D6 §5
 * — the seam that never drains); everything else stays warm-white.
 */
import { useEffect, useState } from "react";

import { fetchEstate } from "../api/genui";
import { fetchExecutions, type RunSummary } from "../api/entities";
import { connectEstateStream, applyStreamEvent } from "../estate/live";
import type { EstateSnapshot } from "../renderers/world/layout";

export interface DistrictLoaders {
  estate: typeof fetchEstate;
  executions: typeof fetchExecutions;
  stream: typeof connectEstateStream;
}

const REAL: DistrictLoaders = {
  estate: fetchEstate,
  executions: fetchExecutions,
  stream: connectEstateStream,
};

interface DistrictColleague {
  entity_id: string;
  name: string;
  autonomy: string;
  hand_raised: boolean;
  state: string;
}

function minutes(run: RunSummary): string {
  if (run.execution_time_ms === null) return "";
  const total = Math.round(run.execution_time_ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function DistrictSheet({
  code,
  onOpenDossier,
  loaders = REAL,
}: {
  code: string;
  onOpenDossier: (colleague: { id: string; name: string }) => void;
  loaders?: DistrictLoaders;
}): JSX.Element {
  const [estate, setEstate] = useState<EstateSnapshot | null>(null);
  const [failed, setFailed] = useState(false);
  const [runs, setRuns] = useState<RunSummary[]>([]);

  useEffect(() => {
    let alive = true;
    let dispose: (() => void) | null = null;
    void (async () => {
      try {
        const snapshot = (await loaders.estate()) as unknown as EstateSnapshot;
        if (!alive) return;
        setEstate(snapshot);
        try {
          dispose = loaders.stream((event) => {
            setEstate((previous) =>
              previous === null ? previous : applyStreamEvent(previous, event),
            );
          });
        } catch {
          // No stream is a slower room, not a broken one.
        }
      } catch {
        if (alive) setFailed(true);
      }
    })();
    void loaders
      .executions()
      .then((loaded) => {
        if (alive) setRuns(loaded);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      dispose?.();
    };
  }, [code, loaders]);

  if (failed) {
    return (
      <p role="alert" data-part="district-failed">
        This district could not be reached.
      </p>
    );
  }
  const district = estate?.districts.find((d) => d.process_code === code);
  if (estate === null || district === undefined) {
    return <p className="vh-quiet">Walking in…</p>;
  }

  const colleagues = (district.colleagues ?? []) as DistrictColleague[];
  const colleagueIds = new Set(colleagues.map((c) => c.entity_id));
  const districtRuns = runs
    .filter((run) => colleagueIds.has(run.entity_id))
    .sort((a, b) => (a.status === "RUNNING" ? -1 : 0) - (b.status === "RUNNING" ? -1 : 0))
    .slice(0, 8);
  const nameOf = new Map(colleagues.map((c) => [c.entity_id, c.name]));
  const treasury = district.treasury as {
    spent: number;
    cap: number;
    reserve_protected: boolean;
  } | null;
  const weather = district.weather as {
    state?: string;
    sentence?: string | null;
  } | null;
  const traffic = (district as { traffic?: { in_1h: number; out_1h: number; parked: number } })
    .traffic;

  return (
    <div className="vh-district" data-part="district-sheet" data-district={code}>
      <header>
        <h2>
          {district.name} <span className="vh-mono">· {code}</span>
        </h2>
      </header>

      <section className="vh-district-panels">
        <div className="vh-district-vitals">
          <ul className="vh-plinth" data-part="plinth">
            {(
              (district as { kpi?: { plinth?: unknown[] } | null }).kpi
                ?.plinth ?? []
            ).map(
              (row, index) => {
                const kpi = row as { label?: string; key?: string; value?: unknown };
                return (
                  <li key={kpi.key ?? index}>
                    <span>{kpi.label ?? kpi.key}</span>{" "}
                    <output>{kpi.value === null || kpi.value === undefined ? "—" : String(kpi.value)}</output>
                  </li>
                );
              },
            )}
          </ul>
          {treasury !== null && treasury !== undefined && (
            <div className="vh-treasury" data-part="treasury">
              <span
                className="vh-treasury-bar"
                style={{
                  width: `${Math.min(100, Math.round((treasury.spent / Math.max(treasury.cap, 0.01)) * 100))}%`,
                }}
              />
              <span className="vh-mono">
                {treasury.spent.toFixed(0)} / {treasury.cap.toFixed(0)}
              </span>
              {treasury.reserve_protected && (
                <span className="vh-reserve" data-part="reserve" title="the protected reserve — the seam that never drains">
                  ▮ reserve
                </span>
              )}
            </div>
          )}
          {weather !== null && weather !== undefined && weather.sentence !== null && (
            <p className="vh-quiet" data-part="weather-sentence">
              {weather.sentence}
            </p>
          )}
        </div>

        <div className="vh-district-people">
          <table className="vh-register" data-part="colleagues">
            <tbody>
              {colleagues.map((colleague) => (
                <tr key={colleague.entity_id}>
                  <td>
                    <button
                      type="button"
                      className="vh-quiet-link"
                      data-part="open-dossier"
                      onClick={() =>
                        onOpenDossier({
                          id: colleague.entity_id,
                          name: colleague.name,
                        })
                      }
                    >
                      {colleague.name}
                    </button>
                  </td>
                  <td className="vh-mono">{colleague.autonomy}</td>
                  <td>
                    {colleague.hand_raised ? (
                      <span className="vh-hand" data-part="hand-raised">
                        ◈ hand raised
                      </span>
                    ) : (
                      colleague.state
                    )}
                  </td>
                </tr>
              ))}
              {colleagues.length === 0 && (
                <tr>
                  <td>
                    <p className="vh-quiet">Nobody works here yet.</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>

          <div className="vh-live-runs" data-part="live-runs">
            <h3 className="vh-eyebrow">live runs</h3>
            {districtRuns.length === 0 ? (
              <p className="vh-quiet">Nothing is running right now.</p>
            ) : (
              <ul>
                {districtRuns.map((run) => (
                  <li key={run.id} data-run-status={run.status}>
                    ▸ {nameOf.get(run.entity_id) ?? "someone"} ·{" "}
                    {run.status.toLowerCase()}
                    {run.execution_time_ms !== null && (
                      <span className="vh-mono"> {minutes(run)}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      {traffic !== undefined && (
        <footer className="vh-district-traffic" data-part="traffic">
          in ▸ {traffic.in_1h}/h · out ▸ {traffic.out_1h}/h · parked ▸{" "}
          {traffic.parked}
        </footer>
      )}
    </div>
  );
}
