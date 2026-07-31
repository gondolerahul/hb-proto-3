/**
 * The colleague dossier / one-on-one (DRIVER D4, D6 §6).
 *
 * Recent decisions are TOLD, not logged — each run is a sentence, with
 * the trace one flip away (the same relationship every narrative surface
 * has to its data). Honest absences stay absent: no per-colleague SLO is
 * measured yet, and the surface says so rather than drawing empty dials.
 *
 * Feedback is an echo and an input: it reaches the bus (and Pragya's
 * channel) now; folding it into the charter runs through SEGA's proposal
 * path when the steward opens (G3) — said on screen, never implied
 * otherwise.
 */
import { useEffect, useState } from "react";

import {
  artKeyFor,
  fetchEntity,
  fetchExecutions,
  fetchTrace,
  type EntityOut,
  type RunSummary,
} from "../api/entities";
import { emitEcho } from "../api/genui";
import { Portrait } from "../components/portraits/Portrait";
import { announce } from "./ribbon";

export interface DossierLoaders {
  entity: typeof fetchEntity;
  executions: typeof fetchExecutions;
  trace: typeof fetchTrace;
  echo: typeof emitEcho;
}

const REAL: DossierLoaders = {
  entity: fetchEntity,
  executions: fetchExecutions,
  trace: fetchTrace,
  echo: emitEcho,
};

function decisionSentence(run: RunSummary): string {
  const when = (run.completed_at ?? run.created_at).slice(0, 10);
  if (run.status === "COMPLETED") {
    return `Finished a piece of work on ${when}.`;
  }
  if (run.status === "RUNNING") {
    return "Is working on something right now.";
  }
  if (run.status === "FAILED") {
    return `Hit a wall on ${when}: ${run.error_message ?? "no reason recorded"}.`;
  }
  if (run.status === "PAUSED") {
    return `Paused on ${when} — waiting on an approval or a person.`;
  }
  return `${run.status.toLowerCase()} on ${when}.`;
}

function TraceFlip({
  runId,
  loaders,
}: {
  runId: string;
  loaders: DossierLoaders;
}): JSX.Element {
  const [trace, setTrace] = useState<unknown>(null);
  const [open, setOpen] = useState(false);
  return (
    <details
      data-part="trace-flip"
      onToggle={(event) => {
        const now = (event.target as HTMLDetailsElement).open;
        setOpen(now);
        if (now && trace === null) {
          void loaders
            .trace(runId)
            .then((loaded) => {
              setTrace(loaded);
              void loaders.echo({
                sentence: `opened run ${runId.slice(0, 8)}'s trace`,
                action_ref: { kind: "dossier.trace", surface_id: "dossier" },
              });
            })
            .catch(() => setTrace({ error: "the trace could not be fetched" }));
        }
      }}
    >
      <summary className="vh-quiet-link">▸ trace</summary>
      {open && (
        <pre className="vh-trace">
          {trace === null ? "fetching…" : JSON.stringify(trace, null, 2)}
        </pre>
      )}
    </details>
  );
}

export function DossierSurface({
  entityId,
  loaders = REAL,
}: {
  entityId: string;
  loaders?: DossierLoaders;
}): JSX.Element {
  const [entity, setEntity] = useState<EntityOut | null>(null);
  const [failed, setFailed] = useState(false);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [feedback, setFeedback] = useState("");
  const [told, setTold] = useState(false);

  useEffect(() => {
    let alive = true;
    void loaders
      .entity(entityId)
      .then((loaded) => {
        if (alive) setEntity(loaded);
      })
      .catch(() => setFailed(true));
    void loaders
      .executions()
      .then((loaded) => {
        if (alive) {
          setRuns(loaded.filter((run) => run.entity_id === entityId).slice(0, 5));
        }
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [entityId, loaders]);

  if (failed) {
    return (
      <p role="alert" data-part="dossier-failed">
        This colleague could not be reached.
      </p>
    );
  }
  if (entity === null) {
    return <p className="vh-quiet">Opening the dossier…</p>;
  }

  const shown = entity.display_name ?? entity.name;
  const governance =
    entity.governance !== null && typeof entity.governance === "object"
      ? entity.governance
      : {};
  const autonomy =
    typeof governance["autonomy_level"] === "string"
      ? governance["autonomy_level"]
      : "A1";

  return (
    <article className="vh-dossier" data-part="dossier">
      <header className="vh-dossier-header">
        <Portrait
          entityKey={artKeyFor(entity.name)}
          entityId={entity.id}
          name={shown}
          size={64}
        />
        <div>
          <h2>{shown}</h2>
          <span className="vh-mono">{autonomy}</span>
          {entity.description !== null && entity.description !== "" && (
            <p className="vh-dossier-line">“{entity.description}”</p>
          )}
        </div>
      </header>

      <section className="vh-dossier-charter" data-part="charter">
        <h3 className="vh-eyebrow">charter</h3>
        <details>
          <summary className="vh-quiet-link">the governance, as JSON</summary>
          <pre className="vh-trace">{JSON.stringify(governance, null, 2)}</pre>
        </details>
      </section>

      <section data-part="slo">
        <h3 className="vh-eyebrow">slo</h3>
        <p className="vh-quiet" data-part="slo-absent">
          No per-colleague SLO is measured yet — when one is, it appears
          here rather than being invented.
        </p>
      </section>

      <section data-part="decisions">
        <h3 className="vh-eyebrow">recent work — told, not logged</h3>
        {runs.length === 0 ? (
          <p className="vh-quiet">Nothing to tell yet.</p>
        ) : (
          <ul className="vh-decisions">
            {runs.map((run) => (
              <li key={run.id}>
                · {decisionSentence(run)} <TraceFlip runId={run.id} loaders={loaders} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <footer className="vh-dossier-tell" data-part="tell">
        <label>
          Tell {shown} something
          <textarea
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            rows={2}
          />
        </label>
        <button
          type="button"
          disabled={feedback.trim() === ""}
          onClick={() => {
            const sentence = `told ${shown}: ${feedback.trim()}`;
            void loaders.echo({
              sentence,
              action_ref: {
                kind: "dossier.feedback",
                surface_id: "dossier",
                params: { entity_id: entity.id },
              },
            });
            announce(sentence);
            setFeedback("");
            setTold(true);
          }}
        >
          tell
        </button>
        {told && (
          <p className="vh-quiet" data-part="tell-honesty">
            Heard, and on the record. It reaches her charter as a proposal —
            never a direct write — once the steward opens that path (G3).
          </p>
        )}
      </footer>
    </article>
  );
}
