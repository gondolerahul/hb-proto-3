/**
 * Registry Halls (DRIVER D3, D6 §7) — full generated CRUD over
 * `tenant_entity_defs`, one hall per HBS module, columns derived from the
 * def so a field SEGA proposed and a human approved appears on the next
 * ask with no deploy.
 *
 * Three properties the record service already guarantees and this surface
 * only RENDERS (never re-implements):
 *
 * - **Owner-writes / others-propose is editability.** A human console
 *   write is a front-door write and applies; an agent's pending proposal
 *   shows as the tracked-change mark (◧) with the delta one click away.
 * - **The master's seal ⊛** marks a per-object SoR-mastered record; its
 *   edits write back through the bridge (Inc-4's machinery, untouched).
 * - **Bulk is T2** — the button drives the certified bulk endpoint, so a
 *   plain session meets the step-up ceremony, never a confirm dialog.
 *
 * CAS conflicts are shown honestly ("someone changed this while you
 *  edited"), and every act echoes (L10).
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { emitEcho } from "../api/genui";
import {
  bulkRecords,
  createRecord,
  deleteRecord,
  fetchDefs,
  fetchProposals,
  fetchRecords,
  updateRecord,
  type EntityDef,
  type EntityDefField,
  type RecordProposal,
  type TenantRecordOut,
} from "../api/tenant";
import {
  StepUpCeremony,
  type CeremonyDeps,
} from "../components/certified/StepUpCeremony";
import { useCertifiedAct } from "../components/certified/useCertifiedAct";
import { announce } from "./ribbon";

export interface HallLoaders {
  defs: typeof fetchDefs;
  records: typeof fetchRecords;
  create: typeof createRecord;
  update: typeof updateRecord;
  remove: typeof deleteRecord;
  bulk: typeof bulkRecords;
  proposals: typeof fetchProposals;
  echo: typeof emitEcho;
  ceremony?: CeremonyDeps;
}

const REAL: HallLoaders = {
  defs: fetchDefs,
  records: fetchRecords,
  create: createRecord,
  update: updateRecord,
  remove: deleteRecord,
  bulk: bulkRecords,
  proposals: fetchProposals,
  echo: emitEcho,
};

function columnsFor(
  def: EntityDef,
  density: "novice" | "operator",
): EntityDefField[] {
  const scalar = def.fields.filter((f) => f.type !== "json");
  return density === "novice" ? scalar.slice(0, 4) : scalar;
}

function cell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return "…";
  return String(value);
}

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: EntityDefField;
  value: unknown;
  onChange: (value: unknown) => void;
}): JSX.Element {
  const id = `field-${field.name}`;
  if (field.type === "enum") {
    return (
      <select
        id={id}
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">—</option>
        {(field.values ?? []).map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }
  const inputType =
    field.type === "date"
      ? "date"
      : ["integer", "number", "money", "decimal"].includes(field.type)
        ? "number"
        : "text";
  return (
    <input
      id={id}
      type={inputType}
      value={value === null || value === undefined ? "" : String(value)}
      onChange={(event) => {
        const raw = event.target.value;
        if (inputType === "number") {
          onChange(raw === "" ? null : Number(raw));
        } else {
          onChange(raw === "" ? null : raw);
        }
      }}
    />
  );
}

function RecordSheet({
  def,
  record,
  proposals,
  loaders,
  onClose,
  onSaved,
}: {
  def: EntityDef;
  record: TenantRecordOut | null; // null = create
  proposals: RecordProposal[];
  loaders: HallLoaders;
  onClose: () => void;
  onSaved: () => void;
}): JSX.Element {
  const [draft, setDraft] = useState<Record<string, unknown>>(
    record?.data ?? {},
  );
  const [problem, setProblem] = useState<string | null>(null);

  const editable = def.fields.filter((f) => f.type !== "json");
  const mine = proposals.filter((p) => p.record_id === record?.id);

  const save = async (): Promise<void> => {
    setProblem(null);
    try {
      if (record === null) {
        const result = await loaders.create(def.name, draft);
        if (result.status !== "applied" && result.record === null) {
          setProblem(result.reason ?? "The record was not created.");
          return;
        }
        void loaders.echo({
          sentence: `created a ${def.name}`,
          action_ref: { kind: "hall.create", surface_id: `hall.${def.module}` },
        });
        announce(`created a ${def.name}`);
      } else {
        const result = await loaders.update(record.id, draft, record.version);
        if (result.status === "conflict") {
          // The CAS is the record service's promise; the surface's job is
          // to say it plainly, never to retry over someone's edit.
          setProblem(
            "Someone changed this record while you edited. Close and reopen to see their version.",
          );
          return;
        }
        void loaders.echo({
          sentence: `edited ${def.name} ${record.id.slice(0, 8)}`,
          action_ref: { kind: "hall.edit", surface_id: `hall.${def.module}` },
        });
        announce(`edited ${def.name}`);
      }
      onSaved();
    } catch (raised) {
      const detail = (
        raised as {
          response?: { data?: { detail?: { detail?: unknown } } };
        }
      ).response?.data?.detail;
      setProblem(
        detail !== undefined
          ? `That did not validate: ${JSON.stringify(detail)}`
          : "That could not be saved.",
      );
    }
  };

  return (
    <section className="vh-record-sheet" data-part="record-sheet">
      <header>
        <h3>
          {record === null ? `New ${def.name}` : `${def.name}`}
          {record?.sor !== null && record?.sor !== undefined && (
            <span
              className="vh-seal"
              data-part="master-seal"
              title={`mastered by ${record.sor}`}
            >
              {" ⊛ "}
              {record.sor}
            </span>
          )}
        </h3>
        <button type="button" className="vh-quiet-link" onClick={onClose}>
          close
        </button>
      </header>

      {mine.length > 0 && (
        <div className="vh-proposals" data-part="proposals">
          {mine.map((proposal) => (
            <div key={proposal.signal_id} className="vh-proposal">
              <span>
                ◧ {proposal.actor ?? "an agent"} proposed:{" "}
                <code>{JSON.stringify(proposal.delta)}</code>
              </span>
              <button
                type="button"
                onClick={() => {
                  setDraft((previous) => ({ ...previous, ...proposal.delta }));
                  void loaders.echo({
                    sentence: `accepted ${proposal.actor ?? "an agent"}'s proposed change to ${def.name}`,
                    action_ref: {
                      kind: "hall.accept-proposal",
                      surface_id: `hall.${def.module}`,
                    },
                  });
                }}
              >
                take into the draft
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="vh-sheet-fields">
        {editable.map((field) => (
          <label key={field.name} htmlFor={`field-${field.name}`}>
            <span>
              {field.name}
              {field.required === true ? " *" : ""}
            </span>
            <FieldInput
              field={field}
              value={draft[field.name]}
              onChange={(value) =>
                setDraft((previous) => ({ ...previous, [field.name]: value }))
              }
            />
          </label>
        ))}
      </div>

      {problem !== null && (
        <p role="alert" data-part="sheet-problem">
          {problem}
        </p>
      )}

      <footer>
        <button type="button" data-part="sheet-save" onClick={() => void save()}>
          {record === null ? "create" : "save"}
        </button>
        {record !== null && (
          <button
            type="button"
            className="vh-quiet-link"
            data-part="sheet-delete"
            onClick={() => {
              void loaders
                .remove(record.id)
                .then(() => {
                  void loaders.echo({
                    sentence: `deleted ${def.name} ${record.id.slice(0, 8)}`,
                    action_ref: {
                      kind: "hall.delete",
                      surface_id: `hall.${def.module}`,
                    },
                  });
                  announce(`deleted ${def.name}`);
                  onSaved();
                })
                .catch(() => setProblem("That could not be deleted."));
            }}
          >
            delete
          </button>
        )}
      </footer>
    </section>
  );
}

function AnalyticsFlip({
  def,
  records,
}: {
  def: EntityDef;
  records: TenantRecordOut[];
}): JSX.Element {
  const enums = def.fields.filter((f) => f.type === "enum");
  const [byField, setByField] = useState(enums[0]?.name ?? "");
  const counts = useMemo(() => {
    const tally = new Map<string, number>();
    for (const record of records) {
      const key = cell(record.data[byField]) || "(unset)";
      tally.set(key, (tally.get(key) ?? 0) + 1);
    }
    return [...tally.entries()].sort((a, b) => b[1] - a[1]);
  }, [records, byField]);

  if (enums.length === 0) {
    return (
      <p className="vh-quiet" data-part="analytics-empty">
        {def.name} has no categorical field to chart yet.
      </p>
    );
  }
  const max = counts[0]?.[1] ?? 1;
  return (
    <div className="vh-analytics" data-part="analytics">
      <label>
        count by{" "}
        <select value={byField} onChange={(e) => setByField(e.target.value)}>
          {enums.map((f) => (
            <option key={f.name} value={f.name}>
              {f.name}
            </option>
          ))}
        </select>
      </label>
      <ul>
        {counts.map(([key, count]) => (
          <li key={key}>
            <span className="vh-bar-label">{key}</span>
            <span
              className="vh-bar"
              style={{ width: `${Math.round((count / max) * 100)}%` }}
            />
            <span className="vh-mono">{count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function HallsSurface({
  density = "novice",
  loaders = REAL,
}: {
  density?: "novice" | "operator";
  loaders?: HallLoaders;
}): JSX.Element {
  const [defs, setDefs] = useState<EntityDef[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [module, setModule] = useState<string | null>(null);
  const [defName, setDefName] = useState<string | null>(null);
  const [records, setRecords] = useState<TenantRecordOut[]>([]);
  const [proposals, setProposals] = useState<RecordProposal[]>([]);
  const [filter, setFilter] = useState("");
  const [flip, setFlip] = useState<"register" | "analytics">("register");
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [sheet, setSheet] = useState<
    { record: TenantRecordOut | null } | null
  >(null);
  const [bulkStatus, setBulkStatus] = useState<string | null>(null);
  const act = useCertifiedAct();

  useEffect(() => {
    void loaders
      .defs()
      .then((loaded) => {
        setDefs(loaded);
        const firstModule = loaded[0]?.module ?? null;
        setModule((current) => current ?? firstModule);
      })
      .catch(() => setFailed(true));
    void loaders
      .proposals()
      .then(setProposals)
      .catch(() => setProposals([]));
  }, [loaders]);

  const modules = useMemo(
    () => [...new Set((defs ?? []).map((d) => d.module))],
    [defs],
  );
  const moduleDefs = useMemo(
    () => (defs ?? []).filter((d) => d.module === module),
    [defs, module],
  );
  const def = moduleDefs.find((d) => d.name === defName) ?? moduleDefs[0];

  const loadRecords = useCallback(() => {
    if (def === undefined) return;
    void loaders
      .records(def.name)
      .then((rows) => {
        setRecords(rows);
        setSelected(new Set());
      })
      .catch(() => setRecords([]));
  }, [def, loaders]);

  useEffect(loadRecords, [loadRecords]);

  if (failed) {
    return (
      <p role="alert" data-part="halls-failed">
        The registry halls could not be reached.
      </p>
    );
  }
  if (defs === null || def === undefined) {
    return <p className="vh-quiet">Opening the halls…</p>;
  }

  const columns = columnsFor(def, density);
  const proposedRecordIds = new Set(
    proposals
      .filter((p) => p.def_name === def.name && p.record_id !== null)
      .map((p) => p.record_id as string),
  );
  const visible = records.filter((record) => {
    if (record.deleted_at !== null) return false;
    if (filter === "") return true;
    return JSON.stringify(record.data)
      .toLowerCase()
      .includes(filter.toLowerCase());
  });

  const runBulk = (op: "update" | "delete", data?: Record<string, unknown>) => {
    const ids = [...selected];
    const sentence =
      op === "delete"
        ? `bulk-deleted ${ids.length} ${def.name} records`
        : `bulk-updated ${ids.length} ${def.name} records`;
    setBulkStatus(null);
    act
      .run(async () => {
        const result = await loaders.bulk(def.name, op, ids, data);
        setBulkStatus(`${result.applied} of ${ids.length} applied`);
        void loaders.echo({
          sentence,
          action_ref: {
            kind: "hall.bulk",
            surface_id: `hall.${def.module}`,
            params: { op, count: ids.length },
          },
        });
        announce(sentence);
        loadRecords();
      })
      .catch(() => setBulkStatus("The bulk act could not be completed."));
  };

  return (
    <div className="vh-hall" data-part="hall" data-hall={def.module}>
      <header className="vh-hall-header">
        <nav className="vh-hall-modules" aria-label="halls">
          {modules.map((name) => (
            <button
              key={name}
              type="button"
              className="vh-quiet-link"
              disabled={name === module}
              onClick={() => {
                setModule(name);
                setDefName(null);
                setSheet(null);
              }}
            >
              {name}
            </button>
          ))}
        </nav>
        <select
          aria-label="object"
          value={def.name}
          onChange={(event) => {
            setDefName(event.target.value);
            setSheet(null);
          }}
        >
          {moduleDefs.map((d) => (
            <option key={d.name} value={d.name}>
              {d.name}
            </option>
          ))}
        </select>
        <input
          aria-label="filter"
          placeholder="filter…"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          onBlur={() => {
            if (filter !== "") {
              void loaders.echo({
                sentence: `filtered ${def.name} to "${filter}"`,
                action_ref: {
                  kind: "register.filter",
                  surface_id: `hall.${def.module}`,
                },
              });
            }
          }}
        />
        <button
          type="button"
          className="vh-quiet-link"
          data-part="flip"
          onClick={() => {
            const next = flip === "register" ? "analytics" : "register";
            setFlip(next);
            void loaders.echo({
              sentence: `flipped ${def.name} to ${next}`,
              action_ref: { kind: "hall.flip", surface_id: `hall.${def.module}` },
            });
          }}
        >
          ⇄ {flip === "register" ? "analytics" : "register"}
        </button>
        {density === "operator" && (
          <span className="vh-mono" data-part="def-version">
            v{def.version} · {def.owner_process_code ?? "unowned"}
          </span>
        )}
      </header>

      {flip === "analytics" ? (
        <AnalyticsFlip def={def} records={visible} />
      ) : (
        <table className="vh-register" data-part="register">
          <thead>
            <tr>
              <th aria-label="select" />
              {columns.map((column) => (
                <th key={column.name}>{column.name}</th>
              ))}
              <th aria-label="marks" />
            </tr>
          </thead>
          <tbody>
            {visible.map((record) => (
              <tr
                key={record.id}
                data-record-id={record.id}
                onClick={() => setSheet({ record })}
              >
                <td
                  onClick={(event) => {
                    event.stopPropagation();
                  }}
                >
                  <input
                    type="checkbox"
                    aria-label={`select ${record.id.slice(0, 8)}`}
                    checked={selected.has(record.id)}
                    onChange={(event) => {
                      setSelected((previous) => {
                        const next = new Set(previous);
                        if (event.target.checked) next.add(record.id);
                        else next.delete(record.id);
                        return next;
                      });
                    }}
                  />
                </td>
                {columns.map((column) => (
                  <td key={column.name}>{cell(record.data[column.name])}</td>
                ))}
                <td>
                  {record.sor !== null && (
                    <span className="vh-seal" data-part="master-seal" title={`mastered by ${record.sor}`}>
                      ⊛
                    </span>
                  )}
                  {proposedRecordIds.has(record.id) && (
                    <span
                      className="vh-tracked"
                      data-part="tracked-change"
                      title="a colleague proposed a change"
                    >
                      ◧
                    </span>
                  )}
                </td>
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={columns.length + 2}>
                  <p className="vh-quiet" data-part="register-empty">
                    No {def.name} records yet.
                  </p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      <footer className="vh-hall-footer">
        <button
          type="button"
          data-part="new-record"
          onClick={() => setSheet({ record: null })}
        >
          new {def.name}
        </button>
        {selected.size > 0 && (
          <span className="vh-bulk-bar" data-part="bulk-bar">
            {selected.size} selected
            <button
              type="button"
              data-part="bulk-delete"
              onClick={() => runBulk("delete")}
            >
              Bulk delete… T2
            </button>
          </span>
        )}
        {bulkStatus !== null && (
          <span className="vh-quiet" data-part="bulk-status">
            {bulkStatus}
          </span>
        )}
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

      {sheet !== null && (
        <RecordSheet
          def={def}
          record={sheet.record}
          proposals={proposals}
          loaders={loaders}
          onClose={() => setSheet(null)}
          onSaved={() => {
            setSheet(null);
            loadRecords();
          }}
        />
      )}
    </div>
  );
}
