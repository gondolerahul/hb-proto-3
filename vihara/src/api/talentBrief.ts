/**
 * The Talent Office's two large reads (D8 E4; R-4 part W) — `GET
 * /ai/talent/brief` and `GET /ai/talent/past-cases`.
 *
 * **Why this file exists at all**, and it is the same reason `dossier.ts`
 * exists: part P wrapped thirteen regions and neither of these was one of them,
 * because E4 shipped after P had been measured. Both routes declare
 * `-> dict[str, Any]`, so `openapi.json` describes them as objects with no
 * properties and `schema.d.ts` has nothing to derive a type from. The shapes
 * below are read off `backend/src/ai/talent/brief_read.py` and
 * `past_cases.py` field by field — which is also why every nullable key here is
 * nullable for a stated reason rather than defensively.
 *
 * `talent.ts` is deliberately not extended: it is another family's file this
 * round, and a new module is the precedent E3 already set.
 *
 * **`absent` is the point of both endpoints and therefore of this module.**
 * Each ships a list naming, per field, what the platform cannot answer and why,
 * so the surface is *told* where to render an absence instead of discovering an
 * empty field and filling it in. `absentIn` is how a region asks; it returns the
 * server's own sentence and nothing else. There is no fallback copy here,
 * because a client-side "not available" would quietly replace nine specific,
 * checkable reasons with one vague one.
 *
 * Two things these shapes deliberately do **not** have:
 *
 *  - **No shortlist.** `_board_run` projects the Meta-Agent board run's id,
 *    status and timings and refuses to project its *output*: "guessing at
 *    candidates from a result blob is exactly the invention this endpoint
 *    refuses". So a brief names the run that would produce candidates and never
 *    the candidates, and no field here can be mistaken for one.
 *  - **No cost, and no verdict.** A case carries what arrived, which records it
 *    turned on and what the run did; `answers` is on the absent list because
 *    nothing joins a candidate to a case, and no per-candidate-month estimate is
 *    served anywhere.
 */
import { api } from "./client";

/** One field the platform cannot answer, with the read model's own reason.
 *  `field` keys are stable — the surface keys regions off them. */
export interface TalentAbsence {
  field: string;
  why: string;
}

/* ────────────────────────────────────────────────────────────────── the brief */

/**
 * The Meta-Agent board run a brief started, where it still exists.
 *
 * `null` when the delegation dispatched no run or the run has been removed —
 * which is a fact about the brief and not a missing field.
 */
export interface BoardRun {
  run_id: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
}

/**
 * One hiring brief: a `capability_build` delegation, projected verbatim.
 *
 * `subject` is deliberately not called `role` — a subject is what the owner
 * asked for, and a job title is a thing nobody wrote. It is `null` where the
 * delegation's `params` carried none.
 */
export interface Brief {
  brief_id: string;
  subject: string | null;
  opened_at: string;
  /** Pragya's own committed sentence about this brief — the only part of the
   *  conversation that is attributably about it. */
  promise: string;
  status: string;
  /** The onboarding stage the delegation was raised at. An integer, and **not**
   *  a position in the five-stage hiring flow — nothing stores one of those. */
  stage: number | null;
  board_run: BoardRun | null;
}

export interface BriefView {
  briefs: Brief[];
  absent: TalentAbsence[];
}

export async function fetchBriefs(limit = 20): Promise<BriefView> {
  return (await api.get<BriefView>("/ai/talent/brief", { params: { limit } })).data;
}

/* ───────────────────────────────────────────────────────────────── the cases */

/** A tenant record a case turned on. `label` is the def plus the head of the id
 *  — the tray's own rule — never a field guessed out of the document. */
export interface CaseRecord {
  record_id: string;
  def: string;
  label: string;
  updated_at: string | null;
  deleted: boolean;
}

/** A ref that names something outside the tenant record plane (`entity:`,
 *  `user:`, `execution_run:`…). Reported rather than dropped: a ref we cannot
 *  read is a fact about the producer. */
export interface OtherRef {
  ref: string;
  kind: string | null;
}

export interface CaseApproval {
  approval_id: string;
  checkpoint_key: string | null;
  checkpoint_trigger: string | null;
  status: string;
  responded_at: string | null;
}

/** What happened: the consuming run, who held it, and the approvals the owner
 *  answered on it. `null` where the consuming run no longer exists. */
export interface CaseOutcome {
  run_id: string;
  status: string;
  completed_at: string | null;
  handled_by: { entity_id: string; name: string; type: string } | null;
  approvals: CaseApproval[];
}

/**
 * One case: a consumed signal, the records it named, and what happened next.
 *
 * `replayable` is three-valued on purpose and the third value is the point. A
 * check that cannot see something must not report it as a refusal, so a case
 * whose refs resolve to nothing is `null` with `unknown_because`, never `false`
 * with a reason it did not earn.
 */
export interface PastCase {
  case_id: string;
  signal_type: string;
  when: string;
  source: string;
  trust: string | null;
  urgency: string | null;
  records: CaseRecord[];
  unresolved_refs: string[];
  other_refs: OtherRef[];
  outcome: CaseOutcome | null;
  replayable: boolean | null;
  blocked_because: string | null;
  unknown_because: string | null;
}

export interface PastCasesView {
  as_of: string;
  cases: PastCase[];
  /** What the flag promises, in the read model's own words. Rendered wherever
   *  the flag is: a claim that lives only in a design document is a claim the
   *  surface will eventually overstate. */
  replayable_means: string;
  max_window_days: number;
  absent: TalentAbsence[];
}

export async function fetchPastCases(limit = 20): Promise<PastCasesView> {
  return (
    await api.get<PastCasesView>("/ai/talent/past-cases", { params: { limit } })
  ).data;
}

/* ───────────────────────────────────────────────────────────────────── absence */

/** The reason this field cannot be answered, or `null` where the endpoint did
 *  not name it as absent. No fallback sentence — see the module note. */
export function absentIn(
  view: { absent: TalentAbsence[] },
  field: string,
): string | null {
  return view.absent.find((item) => item.field === field)?.why ?? null;
}
