/**
 * The Boardroom (DRIVER D6, D6 §8) — where STRAT's pipeline becomes a
 * place, and the increment where Planning records finally get their
 * producer: raising a Proposition and opening Minutes happen HERE, as
 * ordinary tenant-record writes (the record API is their write path by
 * STRAT's own design; adoption alone goes through the certified act).
 *
 * Two honesty rules this surface exists to keep:
 *
 * - **UNTESTED renders as its own thing, never as unknown** (D4 §3.1).
 *   "We never checked" and "we checked and could not tell" must not look
 *   alike — losing that distinction here is what STRAT's fourth grade
 *   value exists to prevent.
 * - **Take-to-Glasshouse is drawn and honestly disabled** — TWIN's
 *   scenario runner is not wired end-to-end until GLASS, and the button
 *   says so instead of pretending.
 */
import { useCallback, useEffect, useState } from "react";

import { emitEcho } from "../api/genui";
import {
  adoptProposition,
  fetchBusinessKpis,
  type BusinessKpi,
} from "../api/strategy";
import {
  createRecord,
  fetchRecords,
  updateRecord,
  type TenantRecordOut,
} from "../api/tenant";
import {
  StepUpCeremony,
  type CeremonyDeps,
} from "../components/certified/StepUpCeremony";
import { useCertifiedAct } from "../components/certified/useCertifiedAct";
import { announce } from "./ribbon";

export interface BoardroomLoaders {
  records: typeof fetchRecords;
  create: typeof createRecord;
  update: typeof updateRecord;
  adopt: typeof adoptProposition;
  kpis: typeof fetchBusinessKpis;
  echo: typeof emitEcho;
  ceremony?: CeremonyDeps;
}

const REAL: BoardroomLoaders = {
  records: fetchRecords,
  create: createRecord,
  update: updateRecord,
  adopt: adoptProposition,
  kpis: fetchBusinessKpis,
  echo: emitEcho,
};

const GRADE_WORDS: Record<string, string> = {
  untested: "UNTESTED — never tried",
  unknown: "UNKNOWN — tried, could not be graded",
  forecast: "FORECAST",
  replay: "REPLAY",
};

function PropositionCard({
  proposition,
  loaders,
  onChanged,
}: {
  proposition: TenantRecordOut;
  loaders: BoardroomLoaders;
  onChanged: () => void;
}): JSX.Element {
  const act = useCertifiedAct();
  const [problem, setProblem] = useState<string | null>(null);
  const data = proposition.data;
  const title = String(data["title"] ?? "an untitled proposition");
  const status = String(data["status"] ?? "draft");
  const grade = String(data["honesty_grade"] ?? "untested");

  const table = (): void => {
    void loaders
      .update(proposition.id, { status: "tabled" }, proposition.version)
      .then((result) => {
        if (result.status === "conflict") {
          setProblem("This proposition moved under you — reopen the board.");
          return;
        }
        void loaders.echo({
          sentence: `tabled the proposition "${title}"`,
          action_ref: { kind: "board.table", surface_id: "boardroom" },
        });
        onChanged();
      })
      .catch(() => setProblem("That could not be tabled."));
  };

  const adopt = (): void => {
    setProblem(null);
    act
      .run(async () => {
        await loaders.adopt({
          proposition_id: proposition.id,
          title,
          decision: String(data["rationale"] ?? title),
        });
        const sentence = `adopted "${title}" as a resolution`;
        void loaders.echo({
          sentence,
          action_ref: {
            kind: "board.adopt",
            surface_id: "boardroom",
            params: { proposition_id: proposition.id },
          },
        });
        announce(sentence);
        onChanged();
      })
      .catch(() => setProblem("The adoption could not be completed."));
  };

  return (
    <article
      className="vh-proposition"
      data-part="proposition"
      data-grade={grade}
      data-status={status}
    >
      <header>
        <h4>{title}</h4>
        <span className="vh-grade" data-part="grade">
          ◦ {GRADE_WORDS[grade] ?? grade.toUpperCase()}
        </span>
      </header>
      {typeof data["rationale"] === "string" && data["rationale"] !== "" && (
        <p>{data["rationale"]}</p>
      )}
      <footer>
        <span className="vh-mono">{status}</span>
        {status === "draft" && (
          <button type="button" data-part="table" onClick={table}>
            table it
          </button>
        )}
        {status === "tabled" && (
          <button type="button" data-part="adopt" onClick={adopt}>
            Adopt as Resolution · T2
          </button>
        )}
        <button
          type="button"
          disabled
          data-part="to-glasshouse"
          title="TWIN's scenario runner wires end-to-end at G5 — until then this button would be a lie"
        >
          take to Glasshouse (opens at G5)
        </button>
      </footer>
      {act.refusal !== null && (
        <StepUpCeremony
          refusal={act.refusal}
          onElevated={act.onElevated}
          onClose={act.onClose}
          deps={loaders.ceremony}
        />
      )}
      {act.error !== null && <p role="alert">{act.error}</p>}
      {problem !== null && <p role="alert">{problem}</p>}
    </article>
  );
}

export function BoardroomSurface({
  onOpenPlanningHall,
  loaders = REAL,
}: {
  onOpenPlanningHall: () => void;
  loaders?: BoardroomLoaders;
}): JSX.Element {
  const [kpis, setKpis] = useState<BusinessKpi[]>([]);
  const [minutes, setMinutes] = useState<TenantRecordOut[]>([]);
  const [propositions, setPropositions] = useState<TenantRecordOut[] | null>(
    null,
  );
  const [failed, setFailed] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newRationale, setNewRationale] = useState("");

  const load = useCallback(() => {
    void loaders
      .records("Proposition")
      .then((rows) =>
        setPropositions(rows.filter((row) => row.deleted_at === null)),
      )
      .catch(() => setFailed(true));
    void loaders
      .records("Minutes")
      .then((rows) => setMinutes(rows.filter((row) => row.deleted_at === null)))
      .catch(() => setMinutes([]));
    void loaders
      .kpis()
      .then(setKpis)
      .catch(() => setKpis([]));
  }, [loaders]);

  useEffect(load, [load]);

  if (failed) {
    return (
      <p role="alert" data-part="board-failed">
        The boardroom could not be reached.
      </p>
    );
  }
  if (propositions === null) {
    return <p className="vh-quiet">Taking a seat…</p>;
  }

  return (
    <div className="vh-board" data-part="boardroom">
      <header className="vh-board-header">
        <h2>Board</h2>
        <button
          type="button"
          className="vh-quiet-link"
          data-part="planning-hall"
          onClick={onOpenPlanningHall}
        >
          ⇄ Planning Hall
        </button>
      </header>

      <section className="vh-board-columns">
        <div className="vh-board-agenda" data-part="agenda">
          <h3 className="vh-eyebrow">she arrives prepared</h3>
          {kpis.length === 0 ? (
            <p className="vh-quiet">
              No measured figures yet — the agenda fills as the KPI series
              grows.
            </p>
          ) : (
            <ul>
              {kpis.map((kpi) => (
                <li key={kpi.key}>
                  · {kpi.label ?? kpi.key}:{" "}
                  {kpi.value === null || kpi.value === undefined ? (
                    <span className="vh-quiet">not measurable yet</span>
                  ) : (
                    <output>{String(kpi.value)}</output>
                  )}
                </li>
              ))}
            </ul>
          )}

          <h3 className="vh-eyebrow">propositions</h3>
          {propositions.length === 0 && (
            <p className="vh-quiet" data-part="no-propositions">
              Nothing has been proposed yet. The first proposition raised
              here is the first Planning record this business produces.
            </p>
          )}
          {propositions.map((proposition) => (
            <PropositionCard
              key={proposition.id}
              proposition={proposition}
              loaders={loaders}
              onChanged={load}
            />
          ))}

          <form
            className="vh-board-raise"
            data-part="raise"
            onSubmit={(event) => {
              event.preventDefault();
              if (newTitle.trim() === "") return;
              void loaders
                .create("Proposition", {
                  title: newTitle.trim(),
                  rationale: newRationale.trim() || null,
                  status: "draft",
                  honesty_grade: "untested",
                })
                .then(() => {
                  const sentence = `raised a proposition on ${newTitle.trim()}`;
                  void loaders.echo({
                    sentence,
                    action_ref: { kind: "board.raise", surface_id: "boardroom" },
                  });
                  announce(sentence);
                  setNewTitle("");
                  setNewRationale("");
                  load();
                });
            }}
          >
            <input
              aria-label="proposition title"
              placeholder="raise a proposition…"
              value={newTitle}
              onChange={(event) => setNewTitle(event.target.value)}
            />
            <input
              aria-label="proposition rationale"
              placeholder="because…"
              value={newRationale}
              onChange={(event) => setNewRationale(event.target.value)}
            />
            <button type="submit">raise</button>
          </form>
        </div>

        <aside className="vh-board-minutes" data-part="minutes">
          <h3 className="vh-eyebrow">minutes</h3>
          {minutes.length === 0 && (
            <p className="vh-quiet">No minutes yet.</p>
          )}
          <ul>
            {minutes.map((entry) => (
              <li key={entry.id}>
                · {String(entry.data["title"] ?? "minutes")}{" "}
                <span className="vh-mono">
                  {String(entry.data["held_on"] ?? "").slice(0, 10)}
                </span>
              </li>
            ))}
          </ul>
          <button
            type="button"
            data-part="open-minutes"
            onClick={() => {
              const title = `Board session ${new Date().toISOString().slice(0, 10)}`;
              void loaders
                .create("Minutes", {
                  title,
                  held_on: new Date().toISOString(),
                })
                .then(() => {
                  void loaders.echo({
                    sentence: `opened minutes: ${title}`,
                    action_ref: { kind: "board.minutes", surface_id: "boardroom" },
                  });
                  load();
                });
            }}
          >
            open minutes
          </button>
        </aside>
      </section>
    </div>
  );
}
