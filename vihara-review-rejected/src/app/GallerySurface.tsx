/**
 * The Gallery (DRIVER D8, D6 §11) — the growth journey: Seasons from the
 * strategy records, mandates with their predicted-vs-realized ghost,
 * colleagues past.
 *
 * Honesty rules this surface exists to keep:
 *
 * - **Portraits of the past are desaturated** by the same rule as the
 *   twin (art bible §7.2) — the past and the not-yet-real share a
 *   material, because neither is currently true.
 * - **`not_measurable` renders as words with its `missing` list**, never
 *   as a zero.
 * - **The KPI series has no backfill** (started 2026-07-25) and the
 *   surface says so instead of rendering an empty chart.
 * - The version ledger has **no read surface yet** (SEGA built the store,
 *   not the API) — an honest absence line, not an empty widget.
 */
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { artKeyFor } from "../api/entities";
import { emitEcho } from "../api/genui";
import { fetchRecords, type TenantRecordOut } from "../api/tenant";
import { Portrait } from "../components/portraits/Portrait";

export interface PastColleague {
  entity_id: string;
  name: string;
  art_name: string;
  terminated_at: string | null;
  runs_total: number | null;
  runs_completed: number | null;
  memo_artifact_id: string | null;
}

export async function fetchColleaguesPast(): Promise<PastColleague[]> {
  return (await api.get<PastColleague[]>("/ai/talent/colleagues-past")).data;
}

export interface RealizedOut {
  kpi_key: string | null;
  predicted_value: number | null;
  realized_value: number | null;
  measurable: boolean;
  missing: string[];
  verdict: string | null;
  honesty_grade: string | null;
}

export async function fetchRealized(mandateId: string): Promise<RealizedOut> {
  return (
    await api.get<RealizedOut>(`/ai/strategy/mandates/${mandateId}/realized`)
  ).data;
}

export interface GalleryLoaders {
  records: typeof fetchRecords;
  past: typeof fetchColleaguesPast;
  realized: typeof fetchRealized;
  echo: typeof emitEcho;
}

const REAL: GalleryLoaders = {
  records: fetchRecords,
  past: fetchColleaguesPast,
  realized: fetchRealized,
  echo: emitEcho,
};

function MandateGhost({
  mandate,
  loaders,
}: {
  mandate: TenantRecordOut;
  loaders: GalleryLoaders;
}): JSX.Element {
  const [ghost, setGhost] = useState<RealizedOut | null>(null);
  const [open, setOpen] = useState(false);
  const title = String(mandate.data["title"] ?? "a mandate");

  return (
    <li className="vh-monument" data-part="monument">
      <span>{title}</span>
      <details
        onToggle={(event) => {
          const now = (event.target as HTMLDetailsElement).open;
          setOpen(now);
          if (now && ghost === null) {
            void loaders
              .realized(mandate.id)
              .then((loaded) => {
                setGhost(loaded);
                void loaders.echo({
                  sentence: `looked at what "${title}" actually did`,
                  action_ref: { kind: "gallery.realized", surface_id: "gallery" },
                });
              })
              .catch(() =>
                setGhost({
                  kpi_key: null,
                  predicted_value: null,
                  realized_value: null,
                  measurable: false,
                  missing: ["the read itself failed"],
                  verdict: null,
                  honesty_grade: null,
                }),
              );
          }
        }}
      >
        <summary className="vh-quiet-link">predicted vs realized</summary>
        {open && ghost !== null && (
          <div className="vh-ghost" data-part="realized">
            {ghost.measurable ? (
              <p>
                predicted <output>{String(ghost.predicted_value)}</output> ·
                realized <output>{String(ghost.realized_value)}</output>
                {ghost.verdict !== null && (
                  <span className="vh-mono"> · {ghost.verdict}</span>
                )}
              </p>
            ) : (
              <p data-part="not-measurable">
                Cannot be measured yet
                {ghost.missing.length > 0 &&
                  ` — missing: ${ghost.missing.join(", ")}`}
                . That is the honest answer, not a zero.
              </p>
            )}
          </div>
        )}
      </details>
    </li>
  );
}

export function GallerySurface({
  loaders = REAL,
}: {
  loaders?: GalleryLoaders;
}): JSX.Element {
  const [resolutions, setResolutions] = useState<TenantRecordOut[] | null>(null);
  const [mandates, setMandates] = useState<TenantRecordOut[]>([]);
  const [past, setPast] = useState<PastColleague[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    void loaders
      .records("Resolution")
      .then((rows) => setResolutions(rows.filter((r) => r.deleted_at === null)))
      .catch(() => setFailed(true));
    void loaders
      .records("Mandate")
      .then((rows) => setMandates(rows.filter((r) => r.deleted_at === null)))
      .catch(() => setMandates([]));
    void loaders
      .past()
      .then(setPast)
      .catch(() => setPast([]));
  }, [loaders]);

  if (failed) {
    return (
      <p role="alert" data-part="gallery-failed">
        The gallery could not be reached.
      </p>
    );
  }
  if (resolutions === null) {
    return <p className="vh-quiet">Walking the gallery…</p>;
  }

  const seasons = [...resolutions].sort((a, b) =>
    String(a.data["adopted_on"] ?? "").localeCompare(
      String(b.data["adopted_on"] ?? ""),
    ),
  );

  return (
    <div className="vh-gallery" data-part="gallery">
      <section data-part="seasons">
        <h3 className="vh-eyebrow">seasons</h3>
        {seasons.length === 0 ? (
          <p className="vh-quiet" data-part="seasons-empty">
            The first season begins with the first adopted resolution — the
            Boardroom is where one is raised.
          </p>
        ) : (
          <ol className="vh-seasons">
            {seasons.map((resolution) => (
              <li key={resolution.id}>
                <span className="vh-mono">
                  {String(resolution.data["adopted_on"] ?? "")}
                </span>{" "}
                {String(resolution.data["title"] ?? "a resolution")}
              </li>
            ))}
          </ol>
        )}
        <p className="vh-quiet" data-part="kpi-honesty">
          The KPI series began 2026-07-25 with no backfill — for a while
          this gallery is honest about having little to show.
        </p>
      </section>

      <section data-part="monuments">
        <h3 className="vh-eyebrow">mandates, and their ghosts</h3>
        {mandates.length === 0 ? (
          <p className="vh-quiet">No mandates stand yet.</p>
        ) : (
          <ul className="vh-monuments">
            {mandates.map((mandate) => (
              <MandateGhost key={mandate.id} mandate={mandate} loaders={loaders} />
            ))}
          </ul>
        )}
      </section>

      <section data-part="colleagues-past">
        <h3 className="vh-eyebrow">colleagues past</h3>
        {past.length === 0 ? (
          <p className="vh-quiet">Nobody has left.</p>
        ) : (
          <ul className="vh-past">
            {past.map((colleague) => (
              <li
                key={colleague.entity_id}
                className="vh-past-colleague"
                data-part="past-colleague"
              >
                <span className="vh-desaturated">
                  <Portrait
                    entityKey={artKeyFor(colleague.art_name)}
                    entityId={colleague.entity_id}
                    name={colleague.name}
                    size={40}
                  />
                </span>
                <span>{colleague.name}</span>
                <span className="vh-quiet">
                  {colleague.runs_completed ?? 0} pieces of work stand ·
                  left {String(colleague.terminated_at ?? "").slice(0, 10)} ·
                  memo in the Library
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="vh-quiet" data-part="ledger-absent">
        Every version of every colleague is in SEGA's ledger; its read
        surface has not been built, so the diffs are not drawn yet rather
        than drawn empty.
      </p>
    </div>
  );
}
