/**
 * The Talent Office (DRIVER D7, D6 §9) — candidates on the left,
 * colleagues on the right, and the two lifecycle acts between them.
 *
 * - **Hire lands at A1**, always: the band is forced at the client AND
 *   the template's own band is discarded, because raising autonomy is
 *   the certified act and hiring at the floor is not.
 * - **The interview is a twin session** and TWIN's runner wires at G5 —
 *   the affordance is drawn and honestly disabled (the Boardroom rule).
 * - **Termination is a plain governed act** (owner decision): the exit
 *   flow shows the tenure, files the handover memo, and a refusal over
 *   live runs is shown as the platform's own sentence — never retried
 *   over half-done work.
 */
import { useCallback, useEffect, useState } from "react";

import { artKeyFor, type EntityOut } from "../api/entities";
import { emitEcho } from "../api/genui";
import {
  fetchEntities,
  fetchTemplates,
  hireFromTemplate,
  parseTerminationRefusal,
  terminateColleague,
} from "../api/talent";
import { Portrait } from "../components/portraits/Portrait";
import { announce } from "./ribbon";

export interface TalentLoaders {
  templates: typeof fetchTemplates;
  entities: typeof fetchEntities;
  hire: typeof hireFromTemplate;
  terminate: typeof terminateColleague;
  echo: typeof emitEcho;
}

const REAL: TalentLoaders = {
  templates: fetchTemplates,
  entities: fetchEntities,
  hire: hireFromTemplate,
  terminate: terminateColleague,
  echo: emitEcho,
};

function CandidateCard({
  template,
  processes,
  loaders,
  onHired,
}: {
  template: EntityOut;
  processes: EntityOut[];
  loaders: TalentLoaders;
  onHired: () => void;
}): JSX.Element {
  const [hiring, setHiring] = useState(false);
  const [processId, setProcessId] = useState(processes[0]?.id ?? "");
  const [name, setName] = useState(template.display_name ?? template.name);
  const [problem, setProblem] = useState<string | null>(null);
  const shown = template.display_name ?? template.name;

  return (
    <article className="vh-candidate" data-part="candidate">
      <header>
        <Portrait
          entityKey={artKeyFor(template.name)}
          entityId={template.id}
          name={shown}
          size={40}
        />
        <h4>{shown}</h4>
      </header>
      {template.description !== null && <p>{template.description}</p>}
      <footer>
        <button
          type="button"
          disabled
          data-part="interview"
          title="the interview is a scoped twin session — TWIN's runner wires end-to-end at G5"
        >
          interview (opens at G5)
        </button>
        {!hiring ? (
          <button
            type="button"
            data-part="hire-open"
            onClick={() => setHiring(true)}
          >
            hire…
          </button>
        ) : (
          <span className="vh-hire-form" data-part="hire-form">
            <input
              aria-label="colleague name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <select
              aria-label="into process"
              value={processId}
              onChange={(event) => setProcessId(event.target.value)}
            >
              {processes.map((process) => (
                <option key={process.id} value={process.id}>
                  {process.display_name ?? process.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              data-part="hire-confirm"
              onClick={() => {
                setProblem(null);
                void loaders
                  .hire(template, processId, name.trim())
                  .then(() => {
                    const sentence = `hired ${name.trim()} at A1`;
                    void loaders.echo({
                      sentence,
                      action_ref: {
                        kind: "talent.hire",
                        surface_id: "talent-office",
                        params: { template_id: template.id },
                      },
                    });
                    announce(sentence);
                    setHiring(false);
                    onHired();
                  })
                  .catch(() => setProblem("The hire could not be completed."));
              }}
            >
              hire at A1
            </button>
          </span>
        )}
      </footer>
      {problem !== null && <p role="alert">{problem}</p>}
    </article>
  );
}

function ColleagueRow({
  colleague,
  loaders,
  onChanged,
}: {
  colleague: EntityOut;
  loaders: TalentLoaders;
  onChanged: () => void;
}): JSX.Element {
  const [refusal, setRefusal] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const shown = colleague.display_name ?? colleague.name;

  return (
    <li className="vh-colleague" data-part="colleague">
      <Portrait
        entityKey={artKeyFor(colleague.name)}
        entityId={colleague.id}
        name={shown}
        size={32}
      />
      <span>{shown}</span>
      {done === null ? (
        <button
          type="button"
          className="vh-quiet-link"
          data-part="terminate"
          onClick={() => {
            setRefusal(null);
            void loaders
              .terminate(colleague.id)
              .then((outcome) => {
                const sentence = `terminated ${outcome.summary.name}; the handover memo is in the Library`;
                void loaders.echo({
                  sentence,
                  action_ref: {
                    kind: "talent.terminate",
                    surface_id: "talent-office",
                    params: { entity_id: colleague.id },
                  },
                });
                announce(sentence);
                setDone(
                  `${outcome.summary.name} has left. ${outcome.summary.runs_completed} pieces of work stand; ` +
                    (outcome.summary.pending_approvals > 0
                      ? `${outcome.summary.pending_approvals} approval(s) remain yours.`
                      : "nothing was left waiting."),
                );
                onChanged();
              })
              .catch((raised: unknown) => {
                const parsed = parseTerminationRefusal(raised);
                setRefusal(
                  parsed !== null
                    ? parsed.reason
                    : "The termination could not be completed.",
                );
              });
          }}
        >
          exit interview & terminate
        </button>
      ) : (
        <span className="vh-quiet" data-part="terminated-note">
          {done}
        </span>
      )}
      {refusal !== null && (
        <p role="alert" data-part="termination-refused">
          {refusal}
        </p>
      )}
    </li>
  );
}

export function TalentSurface({
  loaders = REAL,
}: {
  loaders?: TalentLoaders;
}): JSX.Element {
  const [templates, setTemplates] = useState<EntityOut[] | null>(null);
  const [entities, setEntities] = useState<EntityOut[]>([]);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    void loaders
      .templates()
      .then(setTemplates)
      .catch(() => setFailed(true));
    void loaders
      .entities()
      .then(setEntities)
      .catch(() => setEntities([]));
  }, [loaders]);

  useEffect(load, [load]);

  if (failed) {
    return (
      <p role="alert" data-part="talent-failed">
        The talent office could not be reached.
      </p>
    );
  }
  if (templates === null) {
    return <p className="vh-quiet">Opening the office…</p>;
  }

  const processes = entities.filter(
    (entity) => entity.type === "PROCESS" && entity.status !== "DELETED",
  );
  const colleagues = entities.filter(
    (entity) => entity.type === "AGENT" && entity.status !== "DELETED",
  );

  return (
    <div className="vh-talent" data-part="talent-office">
      <section>
        <h3 className="vh-eyebrow">candidates</h3>
        {templates.length === 0 && (
          <p className="vh-quiet">No candidates are on the bench.</p>
        )}
        {templates.map((template) => (
          <CandidateCard
            key={template.id}
            template={template}
            processes={processes}
            loaders={loaders}
            onHired={load}
          />
        ))}
      </section>
      <section>
        <h3 className="vh-eyebrow">colleagues</h3>
        <ul className="vh-colleagues">
          {colleagues.map((colleague) => (
            <ColleagueRow
              key={colleague.id}
              colleague={colleague}
              loaders={loaders}
              onChanged={load}
            />
          ))}
        </ul>
      </section>
    </div>
  );
}
