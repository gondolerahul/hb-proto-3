/**
 * The Standup (DRIVER D5, D6 §10) — ninety seconds, one card per
 * colleague, arrow-sequenced, each drillable into the dossier.
 *
 * Relayed by Pragya, never spoken by the colleague (L2): the card says
 * "prepared by Ravi", the relaying voice is always hers — and the voice
 * itself is STEWARD's work, so this surface is silent and says nothing
 * that pretends otherwise. Composed client-side from three shipped
 * reads: the estate (who works where), yesterday's executions, and the
 * pending trays.
 */
import { useEffect, useMemo, useState } from "react";

import { fetchExecutions, type RunSummary } from "../api/entities";
import { emitEcho, fetchEstate } from "../api/genui";
import { fetchTrayList } from "../api/trays";
import type { EstateSnapshot } from "../renderers/world/layout";

export interface StandupLoaders {
  estate: typeof fetchEstate;
  executions: typeof fetchExecutions;
  trays: typeof fetchTrayList;
  echo: typeof emitEcho;
}

const REAL: StandupLoaders = {
  estate: fetchEstate,
  executions: fetchExecutions,
  trays: fetchTrayList,
  echo: emitEcho,
};

export interface StandupLine {
  entity_id: string;
  name: string;
  district: string;
  sentences: string[];
  waiting: boolean;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** Pure composition — testable without a wire. */
export function composeStandup(
  estate: EstateSnapshot,
  runs: RunSummary[],
  waitingEntityIds: ReadonlySet<string>,
  now: Date,
): StandupLine[] {
  const since = now.getTime() - DAY_MS;
  const lines: StandupLine[] = [];
  for (const district of estate.districts) {
    for (const colleague of district.colleagues) {
      const theirs = runs.filter(
        (run) =>
          run.entity_id === colleague.entity_id &&
          new Date(run.created_at).getTime() >= since,
      );
      const completed = theirs.filter((r) => r.status === "COMPLETED").length;
      const failed = theirs.filter((r) => r.status === "FAILED").length;
      const running = theirs.filter((r) => r.status === "RUNNING").length;
      const sentences: string[] = [];
      if (completed > 0) {
        sentences.push(
          completed === 1
            ? "Finished one piece of work since yesterday."
            : `Finished ${completed} pieces of work since yesterday.`,
        );
      }
      if (failed > 0) {
        sentences.push(
          failed === 1
            ? "One thing went wrong — it is in the trace."
            : `${failed} things went wrong — they are in the traces.`,
        );
      }
      if (running > 0) {
        sentences.push("Is working on something right now.");
      }
      const waiting = waitingEntityIds.has(colleague.entity_id);
      if (waiting) {
        sentences.push("Is waiting on you.");
      }
      if (sentences.length === 0) {
        sentences.push("A quiet day — nothing to report.");
      }
      lines.push({
        entity_id: colleague.entity_id,
        name: colleague.name,
        district: district.process_code,
        sentences,
        waiting,
      });
    }
  }
  // Whoever needs the owner comes first; quiet days come last.
  return lines.sort((a, b) => Number(b.waiting) - Number(a.waiting));
}

export function StandupSurface({
  onOpenDossier,
  loaders = REAL,
  now = () => new Date(),
}: {
  onOpenDossier: (colleague: {
    id: string;
    name: string;
    district: string;
  }) => void;
  loaders?: StandupLoaders;
  now?: () => Date;
}): JSX.Element {
  const [lines, setLines] = useState<StandupLine[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const [estate, runs, trays] = await Promise.all([
          loaders.estate() as unknown as Promise<EstateSnapshot>,
          loaders.executions(),
          loaders.trays().catch(() => []),
        ]);
        if (!alive) return;
        const waiting = new Set(
          trays
            .map((tray) => tray.prepared_by?.entity_id)
            .filter((id): id is string => typeof id === "string"),
        );
        setLines(composeStandup(estate, runs, waiting, now()));
      } catch {
        if (alive) setFailed(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [loaders, now]);

  const line = useMemo(() => lines?.[index] ?? null, [lines, index]);

  useEffect(() => {
    if (line !== null) {
      void loaders.echo({
        sentence: `opened ${line.name}'s standup line`,
        action_ref: {
          kind: "standup.open",
          surface_id: "standup",
          params: { entity_id: line.entity_id },
        },
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- echo once per card
  }, [index, lines === null]);

  if (failed) {
    return (
      <p role="alert" data-part="standup-failed">
        The standup could not be gathered.
      </p>
    );
  }
  if (lines === null) {
    return <p className="vh-quiet">Gathering the standup…</p>;
  }
  if (lines.length === 0 || line === null) {
    return (
      <p className="vh-quiet" data-part="standup-empty">
        Nobody works here yet — the standup starts when the first colleague
        is hired.
      </p>
    );
  }

  return (
    <div
      className="vh-standup"
      data-part="standup"
      role="region"
      aria-label="the standup"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "ArrowRight") {
          setIndex((i) => Math.min(i + 1, lines.length - 1));
        }
        if (event.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
      }}
    >
      <article className="vh-standup-card" data-part="standup-card">
        <header>
          <span className="vh-eyebrow">
            prepared by {line.name} · relayed by Pragya
          </span>
          {line.waiting && (
            <span className="vh-hand" data-part="standup-waiting">
              ◈
            </span>
          )}
        </header>
        {line.sentences.map((sentence) => (
          <p key={sentence}>{sentence}</p>
        ))}
        <button
          type="button"
          className="vh-quiet-link"
          data-part="standup-drill"
          onClick={() =>
            onOpenDossier({
              id: line.entity_id,
              name: line.name,
              district: line.district,
            })
          }
        >
          open the dossier
        </button>
      </article>
      <footer className="vh-standup-nav">
        <button
          type="button"
          aria-label="previous colleague"
          disabled={index === 0}
          onClick={() => setIndex((i) => i - 1)}
        >
          ←
        </button>
        <span className="vh-mono">
          {index + 1} / {lines.length}
        </span>
        <button
          type="button"
          aria-label="next colleague"
          disabled={index === lines.length - 1}
          onClick={() => setIndex((i) => i + 1)}
        >
          →
        </button>
      </footer>
    </div>
  );
}
