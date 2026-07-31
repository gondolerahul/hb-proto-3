import { useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { Portrait } from "../components/Portrait";
import {
  absenceOf,
  fetchDossier,
  type Dossier,
  type DossierAuthority,
  type DossierCompetency,
} from "../api/dossier";
import { artKeyFor, type EntityOut } from "../api/entities";
import { fetchEntities } from "../api/talent";
import { Bar, Empty, Failed, Lines, Scaffold, useChoice, useResource } from "../lifecycle";
import "./dossier.css";

/**
 * Colleague dossier / one-on-one · depth 2 · S (D6 §6) — on `GET
 * /ai/entities/{id}/dossier` (R-4 part W; the read is D8's E3).
 *
 * **This surface is the reason E3 exists.** It rendered a fixture because
 * nothing served the thing it is about — what this colleague is for, what she
 * may do, and who has to agree — and the round that built the read model made a
 * point of *not* inventing the parts the platform cannot answer. So the payload
 * carries an `absent` list naming, per field and with a reason, what it will not
 * make up. Seven fields are on it, and **all seven are rendered here as
 * absences, in the place the thing would have been, in the endpoint's own
 * words.**
 *
 * That is the whole design decision, and it is a correctness one. A dossier with
 * a decisions column quietly missing looks like a colleague who has decided
 * nothing. A dossier that says *"the decision column is not a read this endpoint
 * can serve, because `GET /ai/executions` takes no parameters at all"* has told
 * the owner something true about their platform. §7.4 says render the gap; this
 * is the surface where there are seven of them, and dropping the explanations to
 * keep the sheet tidy would turn a disciplined read model back into a vague one.
 *
 * ## What is real, and how it is drawn
 *
 * - **The charter is clauses, each naming the column it came from.** A field the
 *   entity was authored without produces no clause at all — "Tone: —" would read
 *   as a setting the platform failed to render. The `source` rides visibly
 *   beside each clause rather than in a tooltip, because "in words" and
 *   "governance record" are two renderings of one thing and a reader should be
 *   able to check that.
 * - **A competency's note is omitted where the registry cannot resolve the
 *   tool**, and `registered: false` is stated as the defect it is. Eight shipped
 *   templates grant `send_email`; the registered tool is `email_send`. The old
 *   surface's `withheld` idiom is kept for it — struck, dimmed *and* labelled,
 *   never dimming alone — with its own word, because "withheld by governance"
 *   and "the platform has never heard of this" are different facts.
 * - **Authority is the gate's answer, printed verbatim.** `evaluate_policy` is
 *   asked with no amount, so a banded category that passes unamounted is
 *   autonomous only *up to* the band — `conditional_on_amount` says so and the
 *   band is printed beside it. Nothing here re-derives the §9.3 matrix: a panel
 *   that computes its own answer eventually disagrees with the control that
 *   actually refuses the act, and the owner believes the panel.
 *
 * ## The dial that is not drawn
 *
 * The old surface had three arc gauges with target ticks. **There is no SLO
 * target anywhere on the platform** — `KpiDefinition` declares a baseline and no
 * target, `HITLCheckpointDef.sla_seconds` is the human reviewer's deadline, and
 * the demotion thresholds are the floor at which autonomy is *removed*. So the
 * gauges are gone rather than rescaled, and `reliability` is readings with the
 * demotion bar named as itself. A reading with an honest "nothing to compare
 * this to" is a measurement; the same reading with an invented 90% beside it is
 * a claim. `failure_rate` is absent rather than `0` when there are no runs.
 *
 * ## The input that was removed
 *
 * The sheet had a "tell her something" form whose text landed in a proposals
 * list. Nothing stores a pending charter-change proposal — that is one of the
 * seven absences — so the form wrote to a `useState` and told the owner it had
 * reached her charter. That is the exact fraud part C names: a control that
 * looks kept and is forgotten. It is gone, and what replaces it is the sentence
 * saying how a charter actually changes.
 *
 * **No certified act lives on this surface.** `certified.autonomy-change` is
 * real (`PUT /ai/entities/{id}`, gated by `raises_autonomy` → `enforce_tier`),
 * and it is deliberately not drawn here: no client has exercised that path, and
 * W is explicit that "it compiles" is not "it works". See the report.
 */

/**
 * What an autonomy band *means to the owner*, in the owner's terms — copy, not
 * data, which is why it lives on the surface rather than coming off the wire.
 * A1/A2 is engineer-speak on a page a business owner reads, so the band is
 * always printed with its consequence. A band this table has not met prints
 * alone rather than borrowing a neighbour's sentence.
 */
const AUTONOMY_MEANS: Record<string, string> = {
  A0: "she proposes, you do everything",
  A1: "she drafts, you approve every act",
  A2: "she acts, and brings the consequential ones to you",
  A3: "she acts, and tells you afterwards",
};

/** The gate's three answers, as an owner reads them. The word is the correct
 *  read; the lamp beside it is only the fast one (§4). */
const DECISION_WORD: Record<string, string> = {
  PASS: "she may act alone",
  RAISE_HITL: "it comes to you first",
  BLOCK: "refused outright",
};

/** Stable empty: a fresh `[]` per render hands `useChoice` a new identity for
 *  no change on screen. */
const NO_ENTITIES: readonly EntityOut[] = [];

/** A gateway is an AGENT tagged `channel:*` — the estate's own predicate,
 *  copied rather than re-invented, so the roster and the district floor hold
 *  the same set of colleagues. */
function isGateway(entity: EntityOut): boolean {
  const tags = entity["tags"];
  return (
    Array.isArray(tags) &&
    tags.some((tag) => typeof tag === "string" && tag.startsWith("channel:"))
  );
}

function nameOf(entity: EntityOut): string {
  return entity.display_name !== null && entity.display_name !== ""
    ? entity.display_name
    : entity.name;
}

/** A percentage from a 0..1 rate. One decimal below 10%, none above — a
 *  "12.7%" beside a "3%" reads as two instruments. */
function percent(rate: number): string {
  const value = rate * 100;
  return `${value < 10 ? value.toFixed(1) : Math.round(value)}%`;
}

export function DossierSurface({
  entityId,
  onEcho,
}: {
  /**
   * The colleague the URL names, where it names one. Optional because
   * `app/Prototype.tsx` does not yet pass `route.subject` down — N2 gives
   * `/dossier/{id}` a subject and the mount drops it, so a deep link currently
   * opens the roster's first colleague. Accepted here rather than ignored so
   * that closing the gap is a one-line change in a file this task does not own.
   */
  entityId?: string;
  onEcho: (msg: string) => void;
}) {
  const entities = useResource(fetchEntities);

  const roster = useMemo(() => {
    if (entities.phase !== "ready") return NO_ENTITIES;
    return entities.value
      .filter(
        (entity) =>
          entity.type === "AGENT" && entity["is_template"] !== true && !isGateway(entity),
      )
      .sort((a, b) => nameOf(a).localeCompare(nameOf(b)));
  }, [entities]);

  const { chosen, choose } = useChoice(
    roster,
    (entity) => entity.id,
    entityId === undefined ? undefined : (entity) => entity.id === entityId,
  );

  if (entities.phase === "pending") return <DossierScaffold />;

  if (entities.phase === "failed") {
    return (
      <section className="do do-flat">
        <Failed what="your colleagues" reason={entities.reason} onRetry={entities.retry} />
      </section>
    );
  }

  /* L2. The whole surface is one colleague, so with no colleagues there is no
     partial room to draw — an empty roster beside an empty sheet would read as
     a dossier that failed to open. It is stated once, as the surface. */
  if (chosen === undefined) {
    return (
      <section className="do do-flat">
        <Empty
          alone
          icon="colleague"
          title="You have not hired anyone yet."
          body="A dossier is a colleague's standing record — their charter in the words it was written in, what they are trusted to decide alone, and how reliably they have done it. There is nothing to keep until somebody is working for you."
        />
      </section>
    );
  }

  return (
    <section className="do">
      <nav className="do-roster" aria-label="Colleagues">
        {roster.map((entity) => (
          <button
            key={entity.id}
            className="do-roster-item"
            data-selected={entity.id === chosen.id || undefined}
            onClick={() => choose(entity.id)}
          >
            <Portrait id={artKeyFor(entity.name)} size={52} />
            <span className="do-roster-name">{nameOf(entity)}</span>
          </button>
        ))}
      </nav>

      {/* `key` is load-bearing, and it is the same reasoning `HallSurface`
          gives: `useResource` captures its reader once on purpose, so the only
          honest way to read a *different* colleague is a different hook
          instance. Remounting also drops the governance flip, which belongs to
          the dossier you were reading and not to the one you just opened. */}
      <Sheet key={chosen.id} entity={chosen} onEcho={onEcho} />
    </section>
  );
}

function Sheet({ entity, onEcho }: { entity: EntityOut; onEcho: (msg: string) => void }) {
  const dossier = useResource(() => fetchDossier(entity.id));

  if (dossier.phase === "pending") return <SheetScaffold />;

  if (dossier.phase === "failed") {
    return (
      <div className="do-sheet">
        <Failed
          what={`${nameOf(entity)}’s dossier`}
          reason={dossier.reason}
          onRetry={dossier.retry}
        />
      </div>
    );
  }

  return <SheetBody dossier={dossier.value} onEcho={onEcho} />;
}

function SheetBody({
  dossier,
  onEcho,
}: {
  dossier: Dossier;
  onEcho: (msg: string) => void;
}) {
  const [asGovernance, setAsGovernance] = useState(false);

  const name = dossier.display_name ?? dossier.name;
  const band = dossier.autonomy.band;
  const means = AUTONOMY_MEANS[band];
  const tools = dossier.competencies.filter((c) => c.kind === "tool").length;
  const connectors = dossier.competencies.filter((c) => c.kind === "connector").length;

  return (
    <div className="do-sheet vh-enter">
      {/* ------------------------------------------------------------- the head */}
      <header className="do-head m-plate m-ticks">
        <Portrait
          id={artKeyFor(dossier.name)}
          size={92}
          title={`${name} — a generated portrait, not a photograph`}
        />
        <div className="do-head-main">
          <span className="t-eyebrow">
            COLLEAGUE
            {dossier.district !== null && ` · ${dossier.district.name.toUpperCase()}`}
          </span>
          <h1 className="do-name t-display">{name}</h1>
          <div className="do-head-chips">
            {/* A chip only where the record carries the field. `role` is
                frequently unauthored and prints nothing rather than "—". */}
            {dossier.role !== null && <span className="m-chip">{dossier.role}</span>}
            <span className="m-chip">{dossier.status.toLowerCase()}</span>
            {dossier.district !== null && (
              <span className="m-chip">{dossier.district.quarter}</span>
            )}
          </div>
          <p className="do-autonomy t-mono">
            {band}
            {means !== undefined && ` — ${means}`}
          </p>
        </div>
        <div className="do-head-side">
          <span className="do-id t-mono">{dossier.entity_id.slice(0, 8)}</span>
          {/* Sanctioned gold (§2.1): an open approval is literally "this needs
              you". Absent, not zeroed, when nothing is waiting. */}
          {dossier.open_approvals > 0 && (
            <span className="do-hand">
              <span className="m-lamp" data-lit data-breathing />
              {dossier.open_approvals} waiting in your tray
            </span>
          )}
          {dossier.running_runs > 0 && (
            <span className="do-doing t-mono">
              {dossier.running_runs} run{dossier.running_runs === 1 ? "" : "s"} in flight
            </span>
          )}
        </div>
      </header>

      {/* -------------------------------------------------- the three absences
          that used to be the top of the sheet. Her own words, her standing and
          what she is doing right now were the first three things a reader met;
          each is now named as unanswerable, with the read model's reason. */}
      <div className="do-absences">
        <Absence
          dossier={dossier}
          field="own_words"
          label="IN HER OWN WORDS"
          lead="Nothing on this sheet is written in her voice."
        />
        <Absence
          dossier={dossier}
          field="standing"
          label="STANDING"
          lead="She holds an autonomy band and no rank."
        />
        <Absence
          dossier={dossier}
          field="probation"
          label="PROBATION"
          lead="Nobody here is on probation, because probation does not exist."
        />
        <Absence
          dossier={dossier}
          field="doing"
          label="RIGHT NOW"
          lead={
            dossier.running_runs > 0
              ? `${dossier.running_runs} run${
                  dossier.running_runs === 1 ? " is" : "s are"
                } in flight and none of them says what it is.`
              : "Nothing is running for her at the moment."
          }
        />
      </div>

      {/* The demotion stamp is the one thing near standing that IS stored, and
          it is only ever present because something happened — so an absent
          stamp means "never demoted", a fact, and not "no data". */}
      {dossier.autonomy.demoted_at !== undefined && (
        <div className="do-probation m-well" role="status">
          <Icon name="alert" size={13} />
          <span className="t-mono">
            demoted to {band} on {dossier.autonomy.demoted_at.slice(0, 10)}
            {dossier.autonomy.demotion_reasons !== undefined &&
              dossier.autonomy.demotion_reasons.length > 0 &&
              ` · ${dossier.autonomy.demotion_reasons.join(" · ")}`}
          </span>
        </div>
      )}

      {/* ------------------------------ charter · competencies · reliability */}
      <div className="do-band">
        <section className="do-cell m-plate">
          <header className="do-cell-head">
            <h2 className="t-eyebrow">CHARTER</h2>
            {/* The flip is the one act this sheet takes, so it is the one that
                echoes (§8). Reading is not an act; changing what you are
                reading is. */}
            <button
              className="m-chip"
              onClick={() => {
                setAsGovernance((v) => !v);
                if (!asGovernance) onEcho(`read ${name}’s governance record`);
              }}
              aria-pressed={asGovernance}
            >
              <Icon name="ledger" size={12} />
              {asGovernance ? "in words" : "governance record"}
            </button>
          </header>
          {asGovernance ? (
            <div className="m-well do-gov-well" data-deep>
              <pre className="do-gov t-mono">
                {JSON.stringify(dossier.charter.governance, null, 2)}
              </pre>
            </div>
          ) : dossier.charter.clauses.length === 0 ? (
            <p className="do-empty">
              This colleague was authored with no goal, no brief, no role and no
              instructions — every field a charter is made of is empty on the
              record. That is a charter nobody has written yet, not one this
              screen failed to read.
            </p>
          ) : (
            <dl className="do-charter">
              {dossier.charter.clauses.map((clause) => (
                <div className="do-clause" key={`${clause.source}:${clause.label}`}>
                  <dt className="t-eyebrow">{clause.label.toUpperCase()}</dt>
                  <dd>{clause.value}</dd>
                  {/* The column it came from, in the open. Two renderings of one
                      thing can only be checked against each other if the reader
                      can see which field each sentence is. */}
                  <dd className="do-source t-mono">{clause.source}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>

        <section className="do-cell m-plate">
          <header className="do-cell-head">
            <h2 className="t-eyebrow">
              COMPETENCIES · {tools} TOOL{tools === 1 ? "" : "S"} · {connectors} CONNECTOR
              {connectors === 1 ? "" : "S"}
            </h2>
          </header>
          {dossier.competencies.length === 0 ? (
            <p className="do-empty">
              Her charter grants no tools, so there is nothing she can call. She
              can be asked for a judgement and cannot act on the estate.
            </p>
          ) : (
            <ul className="do-comps">
              {dossier.competencies.map((competency) => (
                <Competency key={competency.name} competency={competency} />
              ))}
            </ul>
          )}
        </section>

        <section className="do-cell m-plate">
          <header className="do-cell-head">
            <h2 className="t-eyebrow">
              RELIABILITY · LAST {dossier.reliability.window_days} DAYS
            </h2>
          </header>
          <Reliability dossier={dossier} />
        </section>
      </div>

      {/* ------------------------------------------------------- the authority */}
      <section className="do-decisions">
        <header className="do-section-head">
          <h2 className="t-eyebrow">WHAT SHE MAY DECIDE ALONE — THE GATE’S OWN ANSWER</h2>
          <hr className="m-rule-fade do-section-rule" />
        </header>

        {dossier.charter.authority.length === 0 ? (
          <p className="do-empty">
            None of her tools falls in a category the policy matrix governs, so
            there is no band and no checkpoint on her at all. Every act she can
            take is one the platform does not gate.
          </p>
        ) : (
          <div className="vh-stagger">
            {dossier.charter.authority.map((entry, i) => (
              <Authority key={entry.category} entry={entry} index={i} />
            ))}
          </div>
        )}
      </section>

      {/* --------------------------------------------- the two column absences */}
      <section className="do-proposals">
        <header className="do-section-head">
          <h2 className="t-eyebrow">DECISIONS · PROPOSALS</h2>
          <hr className="m-rule-fade do-section-rule" />
        </header>

        <div className="do-absences">
          <Absence
            dossier={dossier}
            field="decisions"
            label="RECENT DECISIONS"
            lead={
              dossier.reliability.runs_total > 0
                ? `${dossier.reliability.runs_total} runs are counted below and none of them can be named here.`
                : "She has run nothing in this window, so there would be nothing to tell."
            }
          />
          <Absence
            dossier={dossier}
            field="charter_proposals"
            label="PROPOSALS"
            lead="Nothing is on the table, and nothing could be."
          />
        </div>

        {/* What replaced the input. The old form put what you typed into local
            state and told you it had reached her charter; there is nowhere for
            it to go, so the honest thing is the sentence about how a charter
            does change. */}
        <p className="do-tell-note t-mono">
          A charter changes by a certified act on the entity itself — you prove
          it is you, and the change is written to the record with your name on
          it. There is no draft step in between and no proposal queue to leave
          something in. Her record stands at version {dossier.version}
          {dossier.charter_updated_at !== null &&
            `, last written ${dossier.charter_updated_at.slice(0, 10)}`}
          .
        </p>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------- an absence -- */

/**
 * One field the platform cannot answer, rendered where the thing would have
 * been.
 *
 * `lead` is the surface's sentence — what an owner needs to know — and `why` is
 * the endpoint's, printed verbatim in `t-mono` at caption size. Both, always:
 * the reason alone is a paragraph of backend prose in the middle of a
 * one-on-one, and the lead alone throws away the only checkable thing on the
 * block. Nothing renders at all if the server did not name this field, because
 * a client-side fallback would silently replace a specific reason with a vague
 * one.
 */
function Absence({
  dossier,
  field,
  label,
  lead,
}: {
  dossier: Dossier;
  field: string;
  label: string;
  lead: string;
}) {
  const why = absenceOf(dossier, field);
  if (why === null) return null;
  return (
    <div className="do-absence m-well">
      <span className="t-eyebrow">{label}</span>
      <p className="do-absence-lead">
        {/* Unlit lamp. An absence is not a fault state — the same reading
            `Empty` takes, and the reason a terracotta dot here would teach an
            owner that their platform is broken rather than young. */}
        <span className="m-lamp" aria-hidden="true" />
        {lead}
      </p>
      <p className="do-absence-why t-mono">{why}</p>
    </div>
  );
}

/* ---------------------------------------------------------- a competency -- */

function Competency({ competency }: { competency: DossierCompetency }) {
  return (
    <li
      className="do-comp"
      data-unregistered={!competency.registered || undefined}
    >
      <span className="do-comp-name t-mono">{competency.name}</span>
      {/* No note is *omitted*, never blanked: the registry could not resolve
          the name, and a description invented for a tool that cannot be called
          would hide a live defect. */}
      <span className="do-comp-note">{competency.note ?? ""}</span>
      {competency.kind === "connector" && (
        <span className="do-comp-kind t-mono">
          {competency.connector_id ?? "connector"}
        </span>
      )}
      {!competency.registered && (
        <span className="do-comp-withheld t-mono">
          <Icon name="alert" size={11} />
          not registered
        </span>
      )}
    </li>
  );
}

/* ----------------------------------------------------------- reliability -- */

/**
 * Readings with nothing to compare them to.
 *
 * There is no arc here and there was one. The three dials this surface used to
 * draw each had a target tick, and no target exists anywhere on the platform to
 * put one at — so the gauge could only ever have been drawn to a number this
 * file chose. What does exist is the demotion bar, which is a floor rather than
 * a goal, and it is named as itself rather than dressed as a target.
 */
function Reliability({ dossier }: { dossier: Dossier }) {
  const { runs_total, runs_failed, failure_rate, p95_latency_ms, demotion_bar } =
    dossier.reliability;
  const slos = absenceOf(dossier, "slos");

  return (
    <>
      <dl className="do-readings">
        <div className="do-reading">
          <dt className="t-eyebrow">RUNS</dt>
          <dd className="t-figure do-reading-val">{runs_total}</dd>
        </div>
        <div className="do-reading">
          <dt className="t-eyebrow">FAILED</dt>
          <dd className="t-figure do-reading-val">{runs_failed}</dd>
        </div>
        <div className="do-reading">
          <dt className="t-eyebrow">FAILURE RATE</dt>
          <dd>
            {/* `null` is not zero. With no runs there is no rate, and "0%"
                would read as "never fails" — the read model refuses to send
                one and this refuses to print one (§7.1). */}
            {failure_rate === null ? (
              <span className="do-reading-absent">
                <span className="m-lamp" aria-hidden="true" />
                no runs in this window, so there is no rate
              </span>
            ) : (
              <span className="t-figure do-reading-val">{percent(failure_rate)}</span>
            )}
          </dd>
        </div>
        <div className="do-reading">
          <dt className="t-eyebrow">P95 LATENCY</dt>
          <dd>
            {p95_latency_ms === null ? (
              <span className="do-reading-absent">
                <span className="m-lamp" aria-hidden="true" />
                nothing timed yet
              </span>
            ) : (
              <span className="t-figure do-reading-val">
                {Math.round(p95_latency_ms)}
                <span className="do-reading-unit">ms</span>
              </span>
            )}
          </dd>
        </div>
      </dl>

      {/* The one line on this block that is a threshold, named as what it is.
          Not a target: nobody promised these numbers, and a bar you fall
          through is not a level you aim for. */}
      <div className="m-well do-bar">
        <span className="t-eyebrow">THE DEMOTION BAR</span>
        <p className="do-bar-text t-mono">
          A level is taken away after {demotion_bar.min_runs} runs if more than{" "}
          {percent(demotion_bar.failure_rate)} of them fail, or if she runs{" "}
          {demotion_bar.latency_multiple}× slower than
          {demotion_bar.latency_floor_ms === null
            ? " her own ceiling — and she declares none, so only the failure rate can demote her."
            : ` her ${Math.round(demotion_bar.latency_floor_ms)}ms ceiling.`}
        </p>
      </div>

      {slos !== null && (
        <div className="do-absence do-absence-flat">
          <span className="t-eyebrow">SERVICE LEVEL</span>
          <p className="do-absence-lead">
            <span className="m-lamp" aria-hidden="true" />
            Nothing above is measured against a promise, because no promise
            exists to measure it against.
          </p>
          <p className="do-absence-why t-mono">{slos}</p>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------- authority -- */

function Authority({ entry, index }: { entry: DossierAuthority; index: number }) {
  const word = DECISION_WORD[entry.decision] ?? entry.decision;
  /* The unit is the platform's own (`CategoryRule.unit`), so "USD" here is the
     matrix stating its denomination rather than this file choosing one. A band
     with `unit: "none"` prints no band at all. */
  const bandText =
    entry.band === null || entry.unit === "none"
      ? null
      : entry.unit === "pct"
        ? `${entry.band}%`
        : entry.unit === "usd"
          ? `USD ${entry.band}`
          : `${entry.band} ${entry.unit}`;

  return (
    <article className="do-decision m-plate" style={{ ["--i" as string]: index }}>
      <header className="do-decision-head">
        <span className="t-eyebrow">{entry.category.replace(/_/g, " ").toUpperCase()}</span>
        {entry.checkpoint_key !== null && (
          <span className="t-mono do-decision-ref">{entry.checkpoint_key}</span>
        )}
      </header>

      <p className="do-verdict">
        {/* Never gold. Gold is "this needs you" or "certified", and a standing
            term of engagement is neither — this is what would happen, not
            something waiting on the owner now (§2.1). */}
        <span
          className="m-lamp"
          data-positive={entry.decision === "PASS" || undefined}
          data-negative={entry.decision === "BLOCK" || undefined}
          aria-hidden="true"
        />
        {word}
        {bandText !== null && ` · up to ${bandText}`}
        {entry.always_hitl && " · no autonomous path exists for this category"}
      </p>

      {/* The gate's own reason, verbatim. This module owns no copy of the §9.3
          matrix and does not paraphrase its answers. */}
      <p className="t-narrative do-decision-told">{entry.reason}</p>

      {entry.conditional_on_amount && (
        <p className="do-conditional t-mono">
          <Icon name="alert" size={11} />
          The real answer depends on the amount, and a dossier describes terms
          rather than an act — so the gate was asked without one. Above the band
          this comes to you.
        </p>
      )}

      <footer className="do-decision-foot">
        {/* Which of her tools reach this category. Named rather than counted:
            "3 tools" is a number you cannot check. */}
        <span className="t-mono do-tools">{entry.tools.join(" · ")}</span>
      </footer>

      {entry.checkpoint_description !== undefined && (
        <p className="do-checkpoint t-mono">
          {entry.checkpoint_description}
          {entry.platform_mandatory === true && " · the platform requires this one"}
          {entry.sla_seconds !== undefined &&
            entry.sla_seconds !== null &&
            ` · you have ${Math.round(entry.sla_seconds / 60)} minutes${
              entry.on_timeout !== undefined ? `, then it ${entry.on_timeout}` : ""
            }`}
        </p>
      )}
    </article>
  );
}

/* -------------------------------------------------------------- scaffolds -- */

/**
 * The pending state (D7 §3.1) — the sheet's own structure with the words not
 * yet in it. No spinner: this is one of the seventeen.
 *
 * Plates first, bars inside them. `vh-skeleton`'s ground is a ~6/255 delta on
 * the raw canvas, so a bar on the page background draws nothing at all.
 */
function DossierScaffold() {
  return (
    /* One `Scaffold`, not two: it carries the single live sentence that speaks
       for every bar on screen, and two of them would announce the same room
       twice. */
    <section className="do do-flat">
      <Scaffold label="The dossier">
        <div className="do-scaffold">
          <div className="do-scaffold-roster">
            {Array.from({ length: 4 }, (_, i) => (
              <div className="do-scaffold-chip m-plate" key={i}>
                <Bar width="xs" />
              </div>
            ))}
          </div>
          <SheetBars />
        </div>
      </Scaffold>
    </section>
  );
}

function SheetScaffold() {
  return (
    <div className="do-sheet">
      <Scaffold label="The dossier">
        <SheetBars />
      </Scaffold>
    </div>
  );
}

function SheetBars() {
  return (
    <div className="do-scaffold-sheet">
      <div className="do-head m-plate">
        <div className="do-scaffold-head">
          <Bar width="xs" />
          <Bar width="md" tall />
          <Bar width="sm" />
        </div>
      </div>
      <div className="do-band">
        {Array.from({ length: 3 }, (_, i) => (
          <div className="do-cell m-plate" key={i}>
            <Bar width="xs" />
            <Lines n={4} />
          </div>
        ))}
      </div>
      <div className="do-decision m-plate">
        <Bar width="sm" />
        <Lines n={3} />
      </div>
    </div>
  );
}
