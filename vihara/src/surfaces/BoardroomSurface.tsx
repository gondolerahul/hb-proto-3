import { useState } from "react";

import { Icon } from "../components/Icon";
import { StepUpCeremony, useCertifiedAct } from "../components/certified";
import {
  Bar,
  Empty,
  Failed,
  Lines,
  Scaffold,
  reasonOf,
  useChoice,
  useResource,
  type Resource,
} from "../lifecycle";
import { adoptProposition, fetchBusinessKpis, type BusinessKpi } from "../api/strategy";
import { fetchRecords, type TenantRecordOut } from "../api/tenant";
import { createScenario } from "../api/twin";
import { Brainstorm } from "./Brainstorm";
import "./boardroom.css";

/**
 * The Boardroom · depth 2 · S (+W setting) (D6 §8) — wired in R-4 part W.
 *
 * Three reads and two writes, all live:
 *
 *   agenda        `GET /ai/kpi/business`
 *   propositions  `GET /ai/tenant/records?def_name=Proposition`
 *   minutes       `GET /ai/tenant/records?def_name=Minutes`
 *   adoption      `POST /ai/strategy/adopt` — **T2, through `useCertifiedAct`**
 *   the Glasshouse `POST /ai/twin/scenarios`
 *
 * The layout is the owner-approved one. What changed is where every field comes
 * from, and — the part worth reading — what this room now refuses to say.
 *
 * ## The rendered gap that was true and is now closed
 *
 * "Take to the Glasshouse" was drawn hard-disabled beside the words *"TWIN's
 * scenario runner is not wired end-to-end"*. That stopped being true on
 * 2026-07-29, and it was **verified end to end before the button was enabled**,
 * not inferred from the router: a scenario created through `POST
 * /ai/twin/scenarios` (201), priced through `/estimate`, queued through `/run`
 * (202), picked up by the arq worker, and read back from
 * `/scenarios/{id}/runs` as a graded `replay` with the engine's own
 * `grade_means`. The same probe confirmed the two refusals this surface has to
 * respect: a run with no acknowledged estimate is a **409 with a sentence**,
 * and an unreachable worker is a 503 — both results, not errors.
 *
 * So the control is live, and it does exactly one thing: it puts the
 * proposition on the shelf. It does **not** price it and does not run it,
 * because twin spend is tenant-initiated (charter decision 6) and a room that
 * spent money on your behalf on the way out of a different room would be the
 * failure that decision exists to prevent.
 *
 * ## What the wiring took away, and why none of it is a redesign
 *
 * §7.1 — a binding that cannot be answered renders **nothing**:
 *
 *  - **The grade's sentence.** `Grade.means` is the engine's own words
 *    (`TwinRunView.grade_means`) and the *record* carries only
 *    `honesty_grade` + `twin_run_id`. There is no `GET /ai/twin/runs/{id}`, and
 *    a proposition holds a run id rather than a scenario id, so this surface
 *    cannot fetch the sentence for a grade it is showing. It prints the grade
 *    and the run id — both real — and says once where the sentence lives.
 *    Composing one here is the thing `twin/grading.py` is explicit about not
 *    letting a client do.
 *  - **Ahead and behind.** The KPI registry declares no direction: there is no
 *    `higher_is_better` anywhere in `kpi/definitions.py`. So a movement is
 *    shown and **not judged** — both figures and the signed difference, with no
 *    positive or negative lamp. Calling a rise in days-sales-outstanding
 *    "ahead" because the number went up is exactly the invented judgement §7
 *    forbids.
 *  - **Authorship.** A `Proposition` record has no author field, so the block
 *    is labelled `TABLED` rather than `FROM HER`, and the rationale carries no
 *    `cite`. "Pragya is listening" is gone with it — nothing on this surface
 *    streams her, and a gold beam for a presence that is not there spends the
 *    §2.1 budget on a claim.
 *  - **Levers, and the sitting's own furniture.** `Proposition` has no levers
 *    field; `SIT-0031`, the opening time and the period were fixture-only.
 *
 * ## Adoption
 *
 * `may_adopt` allows it only from `tabled`, so a proposition in any other
 * status keeps the seal and loses the control, with the server's own rule said
 * in words. The resolution is engraved with the proposition's **own title** as
 * its decision: `AdoptRequest.decision` is required and the platform holds no
 * separate decision text, so restating the proposition is the one thing that
 * can be said without making something up. The card says so.
 */

/* ============================================================= the grade seal */

/** D4 §3.1 / manifest contract §65 — four values, not three. */
export type HonestyGrade = "replay" | "forecast" | "untested" | "unknown";

export interface Grade {
  grade: HonestyGrade;
  /** The run the grade rests on. `null` **only** for `untested`. */
  twinRunId: string | null;
  /**
   * `TwinRunView.grade_means` — the engine's words, never composed here.
   * `null` where the payload carrying the grade does not carry the sentence,
   * which is every Planning record: see the module note.
   */
  means: string | null;
}

const GRADE_WORD: Record<HonestyGrade, string> = {
  replay: "replay",
  forecast: "forecast",
  untested: "untested · never tried",
  unknown: "unknown · could not be graded",
};

const HONESTY_GRADES: readonly HonestyGrade[] = [
  "replay",
  "forecast",
  "untested",
  "unknown",
];

/** The record's `honesty_grade`, or `null` when it holds nothing this client
 *  recognises. Never coerced to `unknown` — "could not be graded" is a real
 *  engine verdict and must not be manufactured by a failed string match. */
export function honestyOf(raw: unknown): HonestyGrade | null {
  return HONESTY_GRADES.find((grade) => grade === raw) ?? null;
}

/**
 * The family's grade idiom, in one place. `compact` renders only the mark and
 * the word — for closed card heads, where the full sentence would shout.
 *
 * The four grades are told apart by **form, not hue**: under the §2.1 gold
 * budget four status colours were never on the table, so each grade is a shape
 * plus a texture plus the engine's own sentence. `replay` is a struck square
 * over a solid strip; `forecast` a dashed square over a dashed strip; `unknown`
 * a slashed square over a broken strip; and `untested` is a hollow CIRCLE with
 * no strip and no run id — the only grade with nothing behind it, rendered as
 * deliberate absence rather than as a fault. The circle-versus-square split
 * keeps untested and unknown apart in greyscale and at a squint, before a
 * single word is read.
 */
export function GradeSeal({ grade, compact = false }: { grade: Grade; compact?: boolean }) {
  return (
    <div className="br-grade" data-grade={grade.grade} data-compact={compact || undefined}>
      <span className="br-grade-mark" aria-hidden="true" />
      <span className="br-grade-word t-eyebrow">{GRADE_WORD[grade.grade]}</span>
      {!compact && (
        <>
          {/* For `untested` this strip stays empty on purpose: there is no run
              to draw a texture of. The blank is the idiom. */}
          <span className="br-grade-strip" aria-hidden="true" />
          <span className="br-grade-run t-mono">
            {grade.twinRunId !== null ? grade.twinRunId : "no run behind it"}
          </span>
          {/* The engine's sentence when the payload carried one, and nothing
              at all when it did not — never a paraphrase. */}
          {grade.means !== null && <p className="br-grade-means t-mono">{grade.means}</p>}
        </>
      )}
    </div>
  );
}

/* =========================================================== reading the wire */

/**
 * Three-digit grouping, by hand and locale-free.
 *
 * Deliberately not `toLocaleString`: it reformats a figure with whatever ICU
 * data the machine happens to carry, so a number changes shape between two
 * browsers — and `en-IN` in particular re-groups into lakhs, which is a claim
 * about the currency nobody made. `TraySurface` keeps its own copy because the
 * certified barrel may not be reached past; this one is shared with the
 * Glasshouse and the Library, exactly as `GradeSeal` already is.
 *
 * It groups and does nothing else: no symbol and no padding. A non-integer is
 * shown to **four** decimals with trailing zeros trimmed, which is the finest
 * grain anything on the wire actually carries (`twin/api.py` rounds
 * `estimate_usd` to four) — two would round a $0.0123 turn down to a cent, and
 * rounding a cost *down* is the one direction a cost may not be moved.
 */
export function grouped(value: number): string {
  const shown = Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  const negative = shown.startsWith("-");
  const bare = negative ? shown.slice(1) : shown;
  const [whole, ...rest] = bare.split(".");
  if (whole === undefined || !/^\d+$/.test(whole)) return shown;
  let out = "";
  for (let i = 0; i < whole.length; i += 1) {
    if (i > 0 && (whole.length - i) % 3 === 0) out += ",";
    out += whole[i]!;
  }
  return `${negative ? "-" : ""}${out}${rest.length > 0 ? `.${rest.join(".")}` : ""}`;
}

/** A string field off a record's `data`, with `""` read as absent — a labelled
 *  row with nothing in it reads as a truncation bug rather than as the honest
 *  answer (§7.1). */
function text(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  if (typeof value !== "string") return null;
  return value.trim() === "" ? null : value;
}

/** A number field, accepting the string a `money`/`decimal` column serialises
 *  as. `NaN` is not a number and is dropped rather than printed. */
function numeric(source: Record<string, unknown>, key: string): number | null {
  const value = source[key];
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/* ==================================================================== agenda */

interface Reading {
  key: string;
  label: string;
  unit: string | null;
  value: number | null;
  baseline: number | null;
  measurable: boolean;
  /** What the platform would need before it could answer. The endpoint's own. */
  missing: string[];
  caveat: string | null;
  windowDays: number | null;
}

function readingOf(kpi: BusinessKpi): Reading {
  const raw = kpi as Record<string, unknown>;
  const missing = raw["missing"];
  return {
    key: kpi.key,
    label: text(raw, "display_name") ?? kpi.label ?? kpi.key,
    unit: text(raw, "unit"),
    value: numeric(raw, "value"),
    baseline: numeric(raw, "baseline_value"),
    measurable: raw["measurable"] === true,
    missing: Array.isArray(missing)
      ? missing.filter((item): item is string => typeof item === "string")
      : [],
    caveat: text(raw, "caveat"),
    windowDays: numeric(raw, "window_days"),
  };
}

type Drift = "unmeasured" | "no-comparison" | "flat" | "moved";

/**
 * The four states the wire can support, and no more.
 *
 * Every lamp here is unlit. `--positive`/`--negative` would be a verdict on the
 * direction, and the registry declares none — the same reasoning the `untested`
 * grade gets, one block down: an absence is not a fault state and a movement is
 * not a failing.
 */
const DRIFT: Record<Drift, string> = {
  unmeasured: "Not measurable",
  "no-comparison": "No comparison yet",
  flat: "Unchanged",
  moved: "Moved",
};

function driftOf(reading: Reading): Drift {
  if (!reading.measurable || reading.value === null) return "unmeasured";
  if (reading.baseline === null) return "no-comparison";
  return reading.value === reading.baseline ? "flat" : "moved";
}

/** A figure in the unit the endpoint named. `currency` gets **no symbol**: the
 *  platform stamps none on a KPI, and a bare figure in a rupee-shaped app is
 *  read as rupees whether or not anyone said so (the `tray_cost` precedent). */
function figureOf(value: number, unit: string | null): string {
  const shown = grouped(value);
  if (unit === "percent") return `${shown}%`;
  if (unit === "days") return `${shown}d`;
  return shown;
}

function Agenda({ readings }: { readings: Reading[] }) {
  const measurable = readings.filter((reading) => reading.measurable).length;
  const stated = readings.some((reading) => reading.unit === "currency");

  return (
    <>
      <header className="br-block-head">
        <span className="t-eyebrow">SHE ARRIVES PREPARED</span>
        <span className="br-block-note t-mono">
          {measurable} of {readings.length} measurable · computed from your records
        </span>
      </header>

      <ul className="br-agenda-list">
        {readings.map((reading) => {
          const drift = driftOf(reading);
          const delta =
            drift === "moved" && reading.value !== null && reading.baseline !== null
              ? reading.value - reading.baseline
              : null;
          return (
            <li className="br-agenda-item" key={reading.key}>
              <span className="br-agenda-state">
                {/* Lamp + word, never colour alone — and never a lit lamp, see
                    the note on DRIFT. */}
                <span className="m-lamp" />
                <span className="br-agenda-word t-eyebrow">{DRIFT[drift]}</span>
                {/* A difference between two figures the endpoint gave, and
                    nothing where there is no second figure. Never 0, never a
                    dash. */}
                {delta !== null && (
                  <span className="br-agenda-delta t-mono">
                    {delta > 0 ? "+" : ""}
                    {figureOf(delta, reading.unit)}
                  </span>
                )}
              </span>

              <span className="br-agenda-text">
                <span className="br-agenda-label t-display">{reading.label}</span>

                {/* Both figures, not only the difference: a delta on its own
                    hides which of the two numbers moved. */}
                {reading.value !== null && (
                  <span className="br-agenda-figs t-mono">
                    <span className="br-agenda-now">
                      {figureOf(reading.value, reading.unit)}
                    </span>
                    {reading.baseline !== null && (
                      <span className="br-agenda-was">
                        was {figureOf(reading.baseline, reading.unit)}
                      </span>
                    )}
                    {reading.windowDays !== null && (
                      <span className="br-agenda-window">
                        over {reading.windowDays} days
                      </span>
                    )}
                  </span>
                )}

                {/* Not measurable is the endpoint's own answer and it names
                    what is missing. Printing a zero here is the single thing
                    `kpi/compute.py` was written to refuse. */}
                {!reading.measurable && reading.missing.length > 0 && (
                  <span className="br-agenda-detail">
                    Not measurable yet — it would need {reading.missing.join(", ")}.
                  </span>
                )}

                {reading.caveat !== null && (
                  <span className="br-agenda-detail">{reading.caveat}</span>
                )}
              </span>
            </li>
          );
        })}
      </ul>

      <p className="br-gap t-mono">
        A movement is shown and not judged: the KPI registry declares no
        direction for any of these, so nothing here says a rise is good news.
        {stated && " Currency figures carry no symbol — the platform stamps none on a KPI."}
      </p>
    </>
  );
}

/* ============================================================== propositions */

interface Tabled {
  /** The record id. It is what `POST /ai/strategy/adopt` takes. */
  id: string;
  title: string | null;
  rationale: string | null;
  expectedEffect: string | null;
  costEstimate: number | null;
  grade: Grade | null;
  status: string | null;
  createdAt: string;
}

function tabledOf(record: TenantRecordOut): Tabled {
  const data = record.data;
  const grade = honestyOf(data["honesty_grade"]);
  return {
    id: record.id,
    title: text(data, "title"),
    rationale: text(data, "rationale"),
    expectedEffect: text(data, "expected_effect"),
    costEstimate: numeric(data, "cost_estimate"),
    grade:
      grade === null
        ? null
        : { grade, twinRunId: text(data, "twin_run_id"), means: null },
    status: text(data, "status"),
    createdAt: record.created_at,
  };
}

/* =================================================================== minutes */

interface FiledMinute {
  id: string;
  title: string | null;
  heldOn: string | null;
  body: string | null;
  decisions: string | null;
  createdAt: string;
}

/**
 * The backend's naive timestamps are UTC by construction (`datetime.utcnow` on
 * a `DateTime` column with no zone), and `Date` parses a naive ISO string as
 * **local** time. Stamping the zone on before parsing is the difference between
 * telling a Chennai owner a meeting was held at 14:30 and telling them it was
 * held at 09:00. `null` rather than a guess when the stamp cannot be read.
 */
function heldLabel(iso: string): string | null {
  const stamped = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const at = new Date(stamped);
  if (Number.isNaN(at.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(at);
}

function minuteOf(record: TenantRecordOut): FiledMinute {
  const data = record.data;
  return {
    id: record.id,
    title: text(data, "title"),
    heldOn: text(data, "held_on"),
    body: text(data, "body"),
    decisions: text(data, "decisions_summary"),
    createdAt: record.created_at,
  };
}

/* ================================================================ the surface */

const readPropositions = () => fetchRecords("Proposition");
const readMinutes = () => fetchRecords("Minutes");

/** Re-read a resource if there is anything to re-read. A read still in flight
 *  has no `retry` by construction — `useResource`'s pending phase carries none,
 *  because a second attempt at an attempt that has not finished is not a
 *  retry — so a write that lands mid-load simply lets the load land. */
function reload<T>(resource: Resource<T>): void {
  if (resource.phase !== "pending") resource.retry();
}

export function BoardroomSurface({ onEcho }: { onEcho: (msg: string) => void }) {
  const kpis = useResource(fetchBusinessKpis);
  const propositions = useResource(readPropositions);
  const minutes = useResource(readMinutes);

  /* Which proposition the adopt call has already taken, so the card can show
     the seal without waiting for the reload to come back. The reload is fired
     too — this is the optimistic half, never the record of truth. */
  const [adopted, setAdopted] = useState<Record<string, string>>({});
  /** Which propositions are now on the Glasshouse shelf, with the scenario id
   *  the server minted. Never composed here, and never shown before the act. */
  const [shelved, setShelved] = useState<Record<string, string>>({});
  /** A failure that is *not* a step-up refusal. `useCertifiedAct` re-throws
   *  those untouched and is right to — a 409 "already adopted" is the
   *  Boardroom's news to break, not a security layer's. */
  const [broke, setBroke] = useState<string | null>(null);

  const act = useCertifiedAct({ renderer: "S", surface: "boardroom", onEcho });

  /* Newest first, off the record's own server-written stamp rather than off
     `held_on`-style text a writer may have supplied in any shape. */
  const list =
    propositions.phase === "ready"
      ? propositions.value
          .map(tabledOf)
          .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
      : NONE;
  const { chosenId: openId, choose } = useChoice(list, (item) => item.id);

  async function adopt(item: Tabled): Promise<void> {
    const title = item.title;
    if (title === null) return;
    setBroke(null);
    try {
      await act.run(
        {
          act: "certified.strategy-resolution",
          echo: `adopted ${title}`,
          summary: `Adopt the proposition “${title}” as a resolution`,
          subject: item.id,
          componentId: "certified.strategy-resolution@1",
        },
        async () => {
          const result = await adoptProposition({
            proposition_id: item.id,
            title,
            /* The proposition restated. `decision` is required and the platform
               holds no separate decision text; the card says so. */
            decision: title,
          });
          /* Reached only when the server took it — and reached again on the one
             retry `run` makes after a ceremony, so there is no second success
             path to keep in step. */
          const resolutionId = result.resolution_id;
          if (resolutionId !== null) {
            setAdopted((previous) => ({ ...previous, [item.id]: resolutionId }));
          }
          reload(propositions);
          reload(minutes);
          const next = list.find(
            (other) => other.id !== item.id && adopted[other.id] === undefined,
          );
          if (next !== undefined) choose(next.id);
        },
      );
    } catch (thrown) {
      setBroke(reasonOf(thrown));
    }
  }

  async function toGlasshouse(item: Tabled): Promise<void> {
    const title = item.title;
    if (title === null) return;
    setBroke(null);
    try {
      /* Name only. `kind` and `scope` are left to the server's own defaults
         rather than invented here — a window this room picked would be a
         claim about the rehearsal it is not entitled to make. */
      const scenario = await createScenario({ name: title });
      setShelved((previous) => ({ ...previous, [item.id]: scenario.id }));
      onEcho(`sent ${title} to the Glasshouse`);
    } catch (thrown) {
      setBroke(reasonOf(thrown));
    }
  }

  if (propositions.phase === "pending") return <BoardroomScaffold />;

  if (propositions.phase === "failed") {
    return (
      <section className="br">
        <Failed
          what="what is tabled in the Boardroom"
          reason={propositions.reason}
          onRetry={propositions.retry}
        />
      </section>
    );
  }

  const waiting = list.filter((item) => adopted[item.id] === undefined);

  return (
    <section className="br">
      {/* ------------------------------------------------------------- header */}
      <header className="br-head">
        <div>
          <span className="t-eyebrow">THE BOARDROOM</span>
          <h1 className="br-title t-display">
            {waiting.length === 0
              ? "Nothing is tabled."
              : `${waiting.length} ${waiting.length === 1 ? "proposition" : "propositions"} tabled`}
          </h1>
        </div>
      </header>

      {broke !== null && (
        <div className="m-plate br-problem" role="status">
          <span className="m-lamp" data-negative aria-hidden="true" />
          <span className="br-problem-text">
            That did not go through, and nothing was decided.
            <span className="br-problem-reason t-mono">{broke}</span>
          </span>
        </div>
      )}

      {act.problem !== null && (
        <div className="m-plate br-problem" role="status">
          <span className="m-lamp" data-negative aria-hidden="true" />
          <span className="br-problem-text">
            {act.problem.message}
            {act.problem.kind === "gap" && (
              <span className="br-problem-reason t-mono">
                Closed by {act.problem.closedBy}.
              </span>
            )}
          </span>
          <button className="m-btn" data-rank="quiet" onClick={act.clearProblem}>
            Dismiss
          </button>
        </div>
      )}

      <div className="br-body">
        <div className="br-main vh-stagger">
          {/* Owner review D: the owner-initiated way in, placed FIRST. What she
              tabled is what she brought; this is what you brought, and a
              boardroom that leads with the chair's agenda every time teaches
              the owner that their own thinking goes second. */}
          <div style={{ ["--i" as string]: 0 }}>
            <Brainstorm onTabled={() => reload(propositions)} onEcho={onEcho} />
          </div>

          {/* ------------------------------------------- she arrives prepared */}
          <section
            className="br-agenda m-plate m-ticks"
            aria-label="Agenda, drawn from the business KPIs"
            style={{ ["--i" as string]: 1 }}
          >
            {kpis.phase === "pending" && (
              <div className="br-ghost" aria-hidden="true">
                <Bar width="sm" />
                <Lines n={3} />
              </div>
            )}
            {kpis.phase === "failed" && (
              <Failed
                what="the agenda"
                alone={false}
                reason={kpis.reason}
                onRetry={kpis.retry}
              />
            )}
            {kpis.phase === "ready" &&
              (kpis.value.length === 0 ? (
                <>
                  <header className="br-block-head">
                    <span className="t-eyebrow">SHE ARRIVES PREPARED</span>
                  </header>
                  <Empty
                    icon="trend"
                    title="There is no agenda this sitting."
                    body="The agenda is the estate's own KPIs, read off your records. The registry has nothing to compute yet, so there is no drift to bring you — this is a quiet estate, not a broken screen."
                  />
                </>
              ) : (
                <Agenda readings={kpis.value.map(readingOf)} />
              ))}
          </section>

          {/* ------------------------------------------------- the propositions */}
          <section className="br-props" aria-label="Propositions" style={{ ["--i" as string]: 2 }}>
            <header className="br-block-head">
              <span className="t-eyebrow">TABLED · PROPOSITIONS</span>
              {list.length > 0 && (
                <span className="br-block-note t-mono">
                  {list.length} on the record · graded before you bet · four grades, not three
                </span>
              )}
            </header>

            {list.length === 0 ? (
              /* L2. A sitting with nothing tabled is not a broken boardroom, and
                 the brainstorm above is still the way in — so the copy points at
                 it rather than leaving the person with a dead column. */
              <Empty
                icon="record"
                title="Pragya has tabled nothing this sitting."
                body="She tables a proposition when she has a bet worth grading and evidence to grade it against; with neither, she says nothing rather than filling the agenda. What you bring above is still the meeting — a matter you file lands in this list."
              />
            ) : (
              <div className="br-props-list">
                {list.map((item) => (
                  <PropositionCard
                    key={item.id}
                    prop={item}
                    open={openId === item.id && adopted[item.id] === undefined}
                    adoptedAs={adopted[item.id]}
                    shelvedAs={shelved[item.id]}
                    busy={act.busy}
                    onOpen={() => choose(item.id)}
                    onAdopt={() => void adopt(item)}
                    onGlasshouse={() => void toGlasshouse(item)}
                  />
                ))}
              </div>
            )}
          </section>
        </div>

        {/* ------------------------------------------------------- the minutes */}
        <aside className="br-minutes m-well" data-deep aria-label="Minutes on the record">
          <header className="br-minutes-head">
            <span className="t-eyebrow">MINUTES</span>
            <span className="br-minutes-live t-mono">as filed</span>
          </header>

          {minutes.phase === "pending" && (
            <div className="br-ghost" aria-hidden="true">
              <Lines n={4} />
            </div>
          )}

          {minutes.phase === "failed" && (
            <Failed
              what="the minutes"
              alone={false}
              reason={minutes.reason}
              onRetry={minutes.retry}
            />
          )}

          {minutes.phase === "ready" &&
            (minutes.value.length === 0 ? (
              /* L2. The dangerous reading of an empty minute book is that the
                 meeting was not recorded; the true one is that nothing has
                 filed a Minutes record, because nothing in the platform does. */
              <Empty
                icon="ledger"
                title="Nothing has been minuted."
                body="Minutes are ordinary Planning records, and no part of the estate writes one on its own — a sitting is minuted when somebody files it. Nothing is missing here; nothing has been written."
              />
            ) : (
              <ol className="br-minutes-list">
                {minutes.value
                  .map(minuteOf)
                  .slice()
                  .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
                  .map((minute) => (
                    <li className="br-minute" key={minute.id}>
                      <span className="br-minute-at t-mono">
                        {minute.heldOn !== null
                          ? (heldLabel(minute.heldOn) ?? minute.heldOn)
                          : (heldLabel(minute.createdAt) ?? "")}
                      </span>
                      <span className="br-minute-mark" aria-hidden="true" />
                      <p className="br-minute-text t-mono">
                        {minute.title !== null && (
                          <span className="br-minute-title">{minute.title}</span>
                        )}
                        {minute.decisions ?? minute.body}
                      </p>
                    </li>
                  ))}
              </ol>
            ))}

          <hr className="m-rule-fade" />
          <footer className="br-minutes-foot">
            <p className="br-minutes-note t-mono">
              Propositions, Minutes and Resolutions are ordinary Planning records
              — the record API is their write path, and adoption is the one act
              it cannot do.
            </p>
          </footer>
        </aside>
      </div>

      {act.ceremony !== null && (
        <StepUpCeremony
          prompt={act.ceremony}
          onElevated={act.onElevated}
          onClose={act.onClose}
        />
      )}
    </section>
  );
}

/** A stable empty collection: a fresh `[]` per render would hand `useChoice` a
 *  new identity on every pass for no change in what is on screen. */
const NONE: readonly Tabled[] = [];

/**
 * The pending state: the Boardroom's own structure, standing, with the words
 * not yet in it (D7 §3.1 — layout first, data second, no spinner on any of the
 * seventeen).
 *
 * The plates are drawn first and the bars go *inside* them. `vh-skeleton`'s
 * ground is a 6/255 delta on the raw canvas, so a bar on the page background
 * draws nothing at all.
 */
function BoardroomScaffold() {
  return (
    <section className="br">
      <Scaffold label="The Boardroom">
        <div className="br-ghost-room">
          <header className="br-head">
            <div className="br-ghost">
              <Bar width="xs" />
              <Bar width="md" tall />
            </div>
          </header>
          <div className="br-body">
            <div className="br-main">
              <div className="m-plate br-ghost-block">
                <Bar width="sm" />
                <Lines n={2} />
              </div>
              <div className="m-plate br-ghost-block">
                <Bar width="sm" />
                <Lines n={3} />
              </div>
              <div className="m-plate br-ghost-block">
                <Bar width="lg" tall />
                <Lines n={2} />
              </div>
            </div>
            <aside className="br-minutes m-well" data-deep>
              <Bar width="xs" />
              <Lines n={5} />
            </aside>
          </div>
        </div>
      </Scaffold>
    </section>
  );
}

function PropositionCard({
  prop,
  open,
  adoptedAs,
  shelvedAs,
  busy,
  onOpen,
  onAdopt,
  onGlasshouse,
}: {
  prop: Tabled;
  open: boolean;
  adoptedAs: string | undefined;
  shelvedAs: string | undefined;
  busy: boolean;
  onOpen: () => void;
  onAdopt: () => void;
  onGlasshouse: () => void;
}) {
  if (adoptedAs !== undefined) {
    return (
      <article className="br-prop br-prop-adopted m-plate">
        <span className="m-medallion br-adopt-seal" aria-hidden="true">
          {/* Same struck check as the Tray's certified seal — one grammar. */}
          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </span>
        <span className="br-adopted-text">{prop.title}</span>
        <span className="t-eyebrow" data-certified>
          ADOPTED · {adoptedAs}
        </span>
      </article>
    );
  }

  /* `may_adopt` in `strategy/pipeline.py`: a proposition becomes a resolution
     from `tabled` and from nothing else. The control is drawn only where the
     server would take it — a button that exists to earn a 409 teaches nothing. */
  const adoptable = prop.status === "tabled" && prop.title !== null;

  return (
    <article className="br-prop m-plate" data-open={open || undefined}>
      <button className="br-prop-head" onClick={onOpen} aria-expanded={open}>
        <span className="br-prop-lead">
          <span className="br-prop-id t-mono">{prop.id}</span>
          {/* §7.1 — `title` is required on the record, so an absent one is a
              record written around the schema. It gets no invented heading. */}
          {prop.title !== null && <h3 className="br-prop-title t-display">{prop.title}</h3>}
        </span>
        <span className="br-prop-right">
          {prop.grade !== null && <GradeSeal grade={prop.grade} compact />}
          {prop.status !== null && (
            <span className="br-prop-at t-mono">{prop.status}</span>
          )}
          <Icon name="chevron" size={14} className="br-caret" />
        </span>
      </button>

      {open && (
        <div className="br-prop-body vh-enter-fade">
          {/* The case for it. No `cite`: a Proposition record names no author,
              and attributing it would be inventing one. */}
          {prop.rationale !== null && (
            <blockquote className="br-because">
              <p className="t-narrative">{prop.rationale}</p>
            </blockquote>
          )}

          {/* A null expectation renders nothing at all — never "₹0", never a
              dash. A board that always sees a number learns every bet has one. */}
          {prop.expectedEffect !== null && (
            <p className="br-expected">
              <Icon name="trend" size={13} className="br-expected-icon" />
              <span className="t-eyebrow">EXPECTED</span>
              <span className="br-expected-val">{prop.expectedEffect}</span>
            </p>
          )}

          {prop.costEstimate !== null && (
            <div className="m-well br-levers" data-deep>
              <dl>
                <div className="br-lever">
                  <dt className="t-eyebrow">COST ESTIMATE</dt>
                  <dd className="br-lever-vals">
                    <span className="t-mono br-lever-to">{grouped(prop.costEstimate)}</span>
                  </dd>
                </div>
              </dl>
              <p className="br-gap t-mono">
                The currency was not stated on this proposition — the record
                carries an amount and the platform stamps no unit on it.
              </p>
            </div>
          )}

          {prop.grade !== null && (
            <div className="m-well br-grade-well">
              <GradeSeal grade={prop.grade} />
              <p className="br-gap t-mono">
                The engine's sentence for this grade lives on the twin run, and
                there is no read for a run by id — only for a scenario's runs.
                So the grade and its run are shown, and the sentence is not
                paraphrased here.
              </p>
            </div>
          )}

          <div className="br-acts">
            {adoptable ? (
              <button
                className="m-btn"
                data-rank="certified"
                disabled={busy}
                onClick={onAdopt}
              >
                <Icon name="key" size={14} />
                Adopt as Resolution
              </button>
            ) : (
              <span className="br-gap t-mono">
                A proposition is adopted from “tabled”, and this one is{" "}
                {prop.status !== null ? `“${prop.status}”` : "carrying no status"}.
                Table it first, so somebody reads it.
              </span>
            )}

            <span className="br-glasshouse">
              {shelvedAs === undefined ? (
                <button className="m-btn" data-rank="quiet" onClick={onGlasshouse}>
                  <Icon name="forward" size={13} />
                  Take to the Glasshouse
                </button>
              ) : (
                <span className="br-gh-done t-mono">
                  <Icon name="check" size={12} />
                  on the shelf as {shelvedAs}
                </span>
              )}
              <span className="br-glasshouse-note t-mono">
                {shelvedAs === undefined
                  ? "This puts it on the Glasshouse shelf. It does not price it and does not run it — a rehearsal costs money, so you start it there, after you have seen the price."
                  : "It is priced and run from the Glasshouse. Nothing has been spent yet."}
              </span>
            </span>
          </div>

          {adoptable && (
            <p className="br-cert-note t-mono">
              <Icon name="seal" size={12} />
              Adoption is a certified act — certified.strategy-resolution@1, T2.
              The estate refuses it until you have proved it is you. The
              resolution is engraved with this proposition's own words: the
              platform holds no separate decision text, and restating it is the
              only thing that can be said here without making something up.
            </p>
          )}
        </div>
      )}
    </article>
  );
}
