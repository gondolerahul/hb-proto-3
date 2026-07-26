# Increment 6 / STRAT — The Strategy Pipeline (closes VG-11)

> **Status:** v1.1 — design, decisions locked (§3). **T1 + T2 done: the object sheets are drafted and ✅ APPROVED (Rahul, 2026-07-26) — [04a_planning_object_sheets.md](./04a_planning_object_sheets.md) is the authoritative field list, and §5 below is corrected to it.** Build (T3 onward) unblocked.
> **Closes:** gap-analysis **VG-11** (the strategy pipeline has no domain model) + the HBS **Planning module** depth Increment 4's "module depth" line omitted.
> **Depends on:** LEARN ([01](./01_learn.md)) — reviews read `kpi_snapshots` · TWIN ([03](./03_twin.md)) — a proposition may carry an honesty grade · the shipped record service, HBS spine and signal bus.
> **Feeds:** Vihara's Boardroom, the Seasons timeline and district monuments (Increment 7).
> **Parent:** [00_overview.md](./00_overview.md) · ratified spec [§15.3](../genui_design_gate_spec.md).

---

## 1. The finding

**VG-11:** *The strategy pipeline has no domain model.* The HBS Planning module contains exactly **one** object — `Budget` (`hbs_seed/__init__.py`, owner process 11, six fields). Meanwhile ratified spec §15.3 describes a five-step business loop the product is supposed to run:

> **Notice** (Minutes) → **Strategize** (Propositions) → **Decide** (Resolutions) → **Act** (Mandates) → **Close the loop** (Reviews)

and states the principle that makes it buildable: *"strategy is data, not prose"*. Today it is neither — it is absent.

Note the scope drift this corrects: Increment 4's road-map line "HBS module depth lands here — Accounting/HRMS/ERP/Legal" **did not name Planning**, and Inc 4 shipped without it. STRAT is that omission, found by walking the Vihara spec against the code.

## 2. Why this belongs in the tenant data plane

The single most consequential decision here is *where these objects live*, and the spec answers it: **records in the Planning Registry Hall**, i.e. the HBS Planning module. Making them HBS objects rather than control-plane tables means they inherit, at no cost:

* the record service — CAS writes, owner-writes/others-propose, the `object.change_proposed` path;
* governance — the PolicyGate categories, HITL checkpoints, SoD;
* per-tenant schema evolution (§10.2) — a tenant can add a field to a Proposition;
* SoR mastering (Inc 4) — a tenant whose board minutes live in another system can master them there;
* the memory-domain viewport, export, and retrieval;
* the Vihara sheet renderer, which re-derives forms from `tenant_entity_defs` with **no frontend change**.

A control-plane `resolutions` table would have re-implemented most of that list, worse. The reverse argument — "strategy is platform machinery" — is wrong on the facts: a Resolution is the tenant's decision about the tenant's business.

## 3. Decisions

1. **Strategy objects are HBS records** (§2), seeded into the spine — not control-plane tables, not a migration.
2. **No tenant `KPI` object.** Targets reference a `kpi_key` from the shipped C6 registry, and actuals come from LEARN's `kpi_snapshots`. Two stores for one number is how a review ends up arguing with the dashboard.
3. **A monument is a rendering of a Resolution, not a second store.** The Resolution carries `district` and `engraved_at`; where it sits on the lawn is Vihara's business (Increment 7).
4. **Adopting a Resolution is a certified human act (T2).** Agents may draft a Proposition; only a human adopts.
5. **Reviews obey the honest-absence rule.** A review whose KPI is not measurable says so; it never reports zero as realized.

## 4. The loop, mapped to mechanism

| Step | Object | What moves it | Governance |
|---|---|---|---|
| **Notice** | `Minutes` | A session — with Pragya, or an owner writing alone. Agents may attach observations | ordinary record write |
| **Strategize** | `Proposition` | Drafted by owner or agent; optionally **tried in the Glasshouse**, which stamps `honesty_grade` + `twin_run_id` | ordinary write; the twin run is TWIN's cost |
| **Decide** | `Resolution` | A human adopts a Proposition. Minuted, engraved, pinned on the Seasons timeline | **T2 certified** (`enforce_kind`) |
| **Act** | `Mandate` | A Resolution issues mandates: what changes, which Process owns it, which Targets it must move, by when | inherits the Resolution's certification; an autonomy raise still hits SEGA's gate |
| **Close** | `Review` | The review date arrives; predicted-vs-realized is computed and written back | ordinary write; the *schedule* is a signal |

The two joins that make the loop a loop:

* **Backward** — *"why does this process exist?"* walks `Mandate → Resolution → Proposition → Minutes`.
* **Forward** — *"did that decision work?"* walks `Resolution → Mandate → Review → measured KPI series`.

Both are `ref` fields on the records. No new join machinery.

## 5. The Planning objects (approved)

**Eight** new HBS objects, module **Planning**, owner process **11** (stored numerically — the de-canary layout lint bans the literal token in `ai/` source, which is why the spine stores `"owner": 11` and renders `P{n:02d}` at seed). Domain tag **`strategy`**, a new member of the closed `DOMAIN_TAGS` set — new because the memory-domain viewport is exactly the thing that should keep board minutes out of a collections agent's retrieval.

> **The review is closed.** The sheets got the treatment the HBS spine got and the Pragya stage scripts got: drafted, reviewed by Rahul, then built. Eleven questions answered 2026-07-26 — see [04a §8](./04a_planning_object_sheets.md#8-review-questions--answered-rahul-2026-07-26), which records the reasoning behind each field name because the schema alone cannot carry it.
>
> **Three fields were renamed in review**, all for the same reason — they are labels a business owner reads: `owner_ref` → **`owner`** (no other ref in the spine carries an `_ref` suffix), `case` → **`rationale`** ("case" reads as a support case in a product that also ships Tickets), and `district` → **`concerns_module`** ("district" is Vihara/Atlas *map* vocabulary; the record should carry business vocabulary and let the surface render the metaphor).

| Object | Core fields |
|---|---|
| **Objective** | `title` (req) · `narrative` text · `horizon` enum(quarter, year, multi_year) · `status` enum(draft, active, achieved, abandoned) · `owner` ref → Employee |
| **Target** | `name` (req) · `kpi_key` string *(a C6 registry key)* · `direction` enum(increase, decrease, hold) · `target_value` decimal · `by_date` date · `objective` ref → Objective · `status` enum(open, met, missed, withdrawn) |
| **Forecast** | `name` (req) · `kpi_key` · `method` enum(manual, twin_forecast, external) · `value` decimal · `interval_low`/`interval_high` decimal · `for_period_start`/`for_period_end` date · `twin_run_id` string (nullable) · `target` ref → Target *(added in review — without it §7.3's predicted-value rule is unimplementable)* |
| **Minutes** | `title` (req) · `held_on` datetime (req) · `attendees` text · `body` text · `decisions_summary` text · `objective` ref (optional) |
| **Proposition** | `title` (req) · `rationale` text · `expected_effect` text · `cost_estimate` money · `honesty_grade` enum(replay, forecast, unknown, untested) default `untested` *(a non-`untested` grade is **refused without a `twin_run_id`** — a grade must have a run behind it)* · `twin_run_id` string (nullable) · `minutes` ref → Minutes · `status` enum(draft, tabled, adopted, rejected, withdrawn) |
| **Resolution** | `title` (req) · `decision` text (req) · `adopted_on` date (req) · `adopted_by` ref → Employee · `proposition` ref → Proposition · `concerns_module` string *(the HBS module it concerns)* · `engraved_at` datetime · `status` enum(active, superseded, revoked) |
| **Mandate** | `title` (req) · `resolution` ref → Resolution (req) · `owning_process` string *(process code)* · `target` ref → Target · `review_due` date (req) · `status` enum(issued, in_flight, reviewed, closed) |
| **Review** | `mandate` ref → Mandate (req) · `reviewed_on` date · `predicted_value` decimal · `realized_value` decimal (nullable) · `measurable` boolean · `missing` text · `verdict` enum(on_track, off_track, met, missed, not_measurable) · `notes` text |

**Spine bookkeeping:** `HBS_SPINE` goes **27 → 35** objects (this doc previously said seven objects and 34 while listing eight; 27 + 8 = 35 — resolved as review question 8.1). **Three** assert sites update in the same commit, not two: `assert len(HBS_SPINE) == 27` in `hbs_seed/__init__.py`, the same assert in `tests/unit/test_tenant_validation.py:109`, and `assert len(bundle["tenant_db"]["entity_defs"]) == 27` in `tests/integration/test_tenant_records_db.py:229` — the export-bundle test the original bookkeeping missed, which would have failed T3. Plus the [`increment-1/03a_hbs_spine.md`](../increment-1/03a_hbs_spine.md) appendix. The asserts exist to make exactly this change deliberate, and they worked.

**Existing tenants get the new objects for free.** `seed_hbs_spine` is additive and idempotent — it inserts only the defs a tenant is missing, and `ensure_ready` calls it on the next provisioning touch after deploy. (The private helper is named `_seed_if_empty`, which is a misnomer worth knowing about: it is a sync, not a first-run seed.) No migration, no backfill job.

## 6. Review scheduling

A `Mandate.review_due` is a promise to come back. Making it real needs a sweep, and it needs to obey L8 (*silence*): a mandate returns to the owner **only** at review time or on exception.

`strategy/review_sweep.py`, arq daily at **02:20 UTC**: for each tenant, mandates whose `review_due` is today and whose status is not `closed` get a `strategy.review_due` signal. Pragya surfaces it as a tray; nothing else interrupts anyone.

The sweep writes no `Review` record — it *asks* for one. A review that the platform fills in by itself is a review nobody read.

## 7. Predicted-vs-realized

`strategy/realized.py`, pure where it can be:

1. From `Mandate → Target`, read `kpi_key` and `target_value`.
2. From LEARN's `kpi_snapshots`, read the series over the mandate window (issue date → `review_due`).
3. `predicted_value` is the Target's value, or the Forecast's if one is attached.
4. `realized_value` is the KPI at review date — **or `None` with `measurable=False` and `missing` populated**, straight from `KpiResult`'s existing shape.
5. If the originating Proposition carries an `honesty_grade`, the review reports it beside the verdict — *"this bet was graded `forecast` when it was made"* is what makes a track record honest rather than flattering.

Rule 4 is the one that matters. The C6 honest-absence rule (`kpi/compute.py`) exists because a fabricated KPI prompts a decision while a missing one prompts a question; a strategy review is precisely where a fabricated number would do the most damage. `verdict = not_measurable` is a legitimate, first-class outcome.

## 8. Governance

* **Adopting a Resolution** — `IntentKind.STRATEGY_RESOLUTION`, tier **T2**, enforced in the handler body via `inward_auth/guard.enforce_kind` (the VG-05 pattern: never a `Depends`, because this repo's router tests call handlers directly). Added to the classifier, to Pragya's `INTENT_SCHEMA` and to the keyword screen together — the `INTENT_SCHEMA` totality test will catch a partial addition, which is what it is for.
* **Agents may draft Propositions, never adopt.** Enforced by the record service's existing owner-writes/others-propose rule plus a check that no agent-originated write sets `Resolution.status='active'`. Mutation-tested.
* **Revoking a Resolution is not gated** — the same asymmetry the VG-05 work established: the safe direction must never be harder than the unsafe one.

## 9. Data model

| Change | Where | Migration |
|---|---|---|
| 7 Planning objects | HBS spine seed (tenant plane) | **none** — seed data |
| `DOMAIN_TAGS` += `strategy` | `hbs_seed/__init__.py` | none |
| `strategy.review_due` signal type | `signals/models.py` | none |
| `IntentKind.STRATEGY_RESOLUTION` | `inward_auth/tiers.py` + Pragya schema | none |

**No Alembic migration in this workstream.** New package **`ai/strategy/`** → `CLEAN_PACKAGES`.

## 10. Task plan

| # | Task | Gate |
|---|---|---|
| **T1** ✅ | Draft the object sheets as a reviewable doc ([04a](./04a_planning_object_sheets.md)) | doc |
| **T2** ✅ | **Rahul reviews the sheets** — closed 2026-07-26, eleven questions answered | — |
| **T3** | Spine additions + `DOMAIN_TAGS` + the **three** 27→35 asserts + the 03a appendix update | unit + `*_db` |
| **T4** | `strategy/pipeline.py` — the five-step transitions as pure functions (a Proposition may only be adopted from `tabled`, a Mandate only issued from an `active` Resolution, …) | unit |
| **T5** | Governance: `STRATEGY_RESOLUTION` T2 + the agents-may-not-adopt rule + the `honesty_grade`-needs-a-run rule (8.5) | unit + `*_db`, **mutation-tested** |
| **T6** | `strategy/review_sweep.py` + the 02:20 cron + `strategy.review_due` | `*_db` |
| **T7** | `strategy/realized.py` — predicted-vs-realized incl. `not_measurable` | unit + `*_db` |
| **T8** | `strategy/api.py` — the pipeline read/write surface over the record service | router + `*_db` |
| **T9** | The TWIN hookup: a Proposition tried in the Glasshouse carries its grade and run id | `*_db` |

## 11. Honest risks

| Risk | Why it is real |
|---|---|
| **This is domain modelling, and the sheets are guesses until reviewed** | Named as T2 rather than assumed away. Field names here are read by owners, not by engineers |
| **Seven objects is a large spine change** | The spine is a *reviewed* artifact; the assert makes the change deliberate, and additive seeding means existing tenants pick it up quietly. Still the largest single-workstream change to the tenant schema since Increment 1 |
| **Empty until a business uses it** | A Solo Pack tenant may never hold a board meeting. The pipeline must be genuinely optional — nothing else in the platform may *require* a Resolution to exist |
| **Reviews will mostly say `not_measurable` at first** | Because `kpi_snapshots` starts empty (LEARN §6.3). That is honest and it will still look like a broken feature; the copy must explain *why* |
| **Two forecast concepts** | TWIN's forecast is an ephemeral run result; Planning's `Forecast` is a committed number the business plans against. Related, not the same. If they merge later, merge toward the record |

## 12. Brainstorm decisions

*(Answered — do not re-litigate.)*

1. **Records or control-plane tables:** HBS records (§2).
2. **KPI object:** none — reference the C6 registry (§3.2).
3. **Monument store:** no separate store (§3.3).
4. **Who adopts:** humans only, T2 (§8).
5. **Missing measurement:** a first-class verdict (§7).
6. **Review scheduling:** a signal, not a table (§6).

---

## 13. Build notes — T1–T9 (2026-07-26, branch `inc6/strat`)

**STRAT is complete, and with it Increment 6.** All of T1–T9. New package `ai/strategy/`; **no Alembic migration** — the largest domain-model change to the tenant schema since Increment 1 adds none, because new HBS objects are seed data.

### 13.1 What shipped

| Task | Where |
|---|---|
| T1 + T2 | [04a](./04a_planning_object_sheets.md) — eight sheets, eleven questions, ✅ approved |
| T3 | Eight objects in `hbs_seed/__init__.py`, `DOMAIN_TAGS += strategy`, the **three** 27→35 asserts, the [03a](../increment-1/03a_hbs_spine.md) appendix |
| T4 | `strategy/pipeline.py` — the transition tables, `check_honesty_grade`, `may_adopt`, `may_issue_mandate`, `validate_write` |
| T5 | `strategy/governance.py` + the new `tenant_schema/write_policy.py` seam; `IntentKind.STRATEGY_RESOLUTION` across tiers + Pragya's schema + the keyword screen + the screen floor |
| T6 | `strategy/review_sweep.py`, `strategy.review_due`, `strategy/crons.py`, the 02:20 cron |
| T7 | `strategy/realized.py` — predicted-vs-realized on C6's honest-absence rule |
| T8 | `strategy/api.py` — `POST /ai/strategy/adopt`, `GET /ai/strategy/mandates/{id}/realized`, `GET /ai/strategy/reviews-due` |
| T9 | `strategy/twin_link.py` — a Glasshouse run's grade, copied never composed |

### 13.2 Five design deltas

**1. Enforcement needed a seam the record service did not have.** The design says the agents-may-not-adopt rule is enforced by "the record service's existing owner-writes/others-propose rule plus a check". There was nowhere to put the check: `RecordService` answers *who may write* and *is the shape valid*, and neither answers *is this change a legal move*. So `tenant_schema/write_policy.py` is a new pluggable seam in exactly the shape KAR used for consent and Inc-4 used for SoR write-back — **policy in `ai/strategy/`, enforcement at the existing call site**, the record service left ignorant of Planning. It also gave the pipeline rules (T4) a caller, which they otherwise would not have had: a transition table nothing routes through is a table, not a guarantee.

The seam **fails open** on an unexpected error, and the asymmetry is deliberate: an object rule is a correctness guard over a tenant's own records, not a security control. Every security control in this codebase fails *closed* and none routes through here.

**2. `RecordResult` needed a `REFUSED` status.** `PROPOSED` is an ownership answer and `CONFLICT` is a race; neither says "the change itself is not a legal move regardless of who asked". Adding the fourth kept the three existing meanings intact rather than overloading one.

**3. The review sweep had to be ORM, not `text()`.** The first draft wrote raw SQL against `tenant.tenant_records`. Tenant routing is a SQLAlchemy `schema_translate_map` (symbolic `tenant` → `t_<hex>`), so a raw statement names a schema that does not exist — there was no precedent for raw tenant-plane SQL anywhere in `src/ai/` and this is why. Recorded in the module docstring so the next person does not rediscover it.

**4. `Mandate.resolution` being required is the sheet working, and it bit the tests first.** The fixture had to build a Resolution before it could build a Mandate. That is the constraint doing its job: a mandate that names no resolution cannot answer *"why does this process exist?"*, and that backward walk is half the point of the loop.

**5. `decide_verdict` has no `met` for a `hold` target.** Holding a number is a state you are still in, not one you reach, so the honest answers are `on_track` and `off_track`. Reporting `met` would claim a finish line that does not exist. The design's §7 did not consider the third direction.

### 13.3 What the gates caught

**LEARN's reward-hacking guarantee fired on STRAT, and it was right to.** `test_no_kpi_key_appears_outside_the_registry_and_learning` greps all of `src/ai` for any C6 key: KPIs are *reported*, never *targeted*, because a key in a prompt or a goal gives an agent an incentive to move the number rather than do the work it measures. Two files tripped it — and in both the key was in an **explanatory comment**, not in code. The code only ever reads `target["kpi_key"]` at runtime, which is exactly right: a tenant's chosen key is a *value flowing through*, never a literal in platform source.

The comments were rewritten. Widening the test to allow `strategy/` was the wrong fix and worth saying why: STRAT is precisely the place where a KPI legitimately becomes a target, so an exemption here would be the one exemption most likely to hide a real violation later.

### 13.4 Honest limits

* **Nothing produces Planning records yet.** The objects seed, the rules hold and the API works, but no agent, no Pragya stage and no wizard step creates a Minutes or a Proposition. STRAT ships the domain and the governance; the surfaces that fill it are Vihara's Boardroom (Increment 7).
* **`GET /ai/strategy/reviews-due` is the only tray.** The sweep emits `strategy.review_due` and nothing consumes it — no Pragya surface renders the signal, so today the tray is a poll rather than a notification.
* **Reviews will mostly say `not_measurable` for a quarter**, because `kpi_snapshots` started 2026-07-25 with no backfill by construction. That is honest, it will still look like a broken feature, and it is why `missing` says *why* rather than only *that*.
* **The TWIN hookup is a reader, not a runner.** `twin_link` copies a grade off an existing run; nothing yet takes a Proposition *to* the Glasshouse. TWIN's own limit is the reason — no scenario runner is wired end-to-end ([03](./03_twin.md) §14.7) — so the two gaps close together or not at all.
* **`concerns_module` is a free string.** It should hold an HBS module name and nothing validates that it does. An enum would have frozen the module list into the tenant schema, which is the mistake decision 3.2 avoided for `kpi_key`; a validator against the live module list is the better fix and belongs with the surface that offers the choice.
* **The agents-may-not-adopt rule is currently unreachable in production** — the ownership gate turns every agent write to a Planning object into a proposal first, because the Planning owner process has no seeded agent. It is tested by simulating the future where one exists, which is the only way to test it honestly today, and it is why the rule is written against `actor_process_code` rather than leaning on the ownership gate.

### 13.5 Gates

typecheck **317** files strict · layout lint (the de-canary lint caught a literal owner code in a docstring — it works) · **1996 unit + parity/eval** (16 parity/eval green) · **490 integration** (+26) · **no migration**; head stays **`lib002`**.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-26 | v1.1 — **T1 + T2 done.** §5 corrected to the approved sheets: **eight** objects and spine **27 → 35** (not seven/34), `owner_ref`→`owner`, `case`→`rationale`, `district`→`concerns_module`, `Forecast.target` added, `honesty_grade` refused without a `twin_run_id`, and a **third** spine-assert site recorded that the original bookkeeping missed. §10's T1/T2 marked done. |
| 2026-07-25 | v1.0 — design written. Strategy placed in the tenant data plane as HBS Planning objects (inheriting record service, governance, evolution, SoR and the Vihara sheet renderer); seven object sheets drafted for owner review as an explicit blocking task; no tenant KPI object and no separate monument store; predicted-vs-realized built on the C6 honest-absence rule with `not_measurable` as a real verdict; review scheduling as a signal; adoption made a T2 certified act following the VG-05 handler-body pattern. |
