# Increment 6 / LEARN — The Learning Store, and the History That Makes It Measurable (closes B10)

> **Status:** v1.2 — design locked (§3). **T1–T3 BUILT** (2026-07-25, branch `inc6/learn`) — build notes §14. T4–T10 pending.
> **Closes:** register **B10** (learning-system risk blindspots) + gap-analysis **VG-12** (no KPI history store).
> **Depends on:** the shipped signal bus (`ai/signals/`), CORTEX Intelligence trees (`ai/memory/intelligence_tree_service.py` + `rule_lifecycle.py`), the C6 KPI registry (`ai/kpi/`), RTR's `routing_decisions` (`ai/intelligence/models.py`), EVX's admission gate (`ai/intelligence/admission.py`).
> **Feeds:** SEGA ([02](./02_sega.md)) — LEARN proposes, SEGA admits · TWIN ([03](./03_twin.md)) — the forecast engine reads `kpi_snapshots` · STRAT ([04](./04_strat.md)) — mandate reviews read the same series · Vihara G1/G2 (Increment 7) — plinth trends and the Seasons timeline.
> **Parent:** [00_overview.md](./00_overview.md) · [00_charter.md](./00_charter.md) (decisions 2, 3, 8).

---

## 1. The findings this workstream exists to fix

**B10 (High):** *Learning System risk blindspots. No treatment of reward hacking (KPI-optimized collections vs the Karuna empathy floor — which wins?), behavioral drift detection, or the cross-tenant question: does router/task learning pool across tenants (data leakage) or stay per-tenant (cold start)?*

B10 is **three findings wearing one number**, and they need separate answers:

| B10's half | The question | Where it is answered |
|---|---|---|
| **Cross-tenant policy** | Does learning pool? | §4 — split, enforced by record shape |
| **Reward hacking** | Which wins, the KPI or the Karuna floor? | §7 — the floor, structurally: KPIs never enter an agent's objective |
| **Drift detection** | How do we notice behaviour changing? | §8 — an observation series feeding C4's shipped demotion sweep |

**VG-12:** *No KPI history store.* `src/ai/kpi/` is `definitions.py` + `compute.py` + `api.py` — **no `models.py`, no persistence**. Every KPI is computed on demand from current records, so the increment whose stated goal is *"Week 12 > Week 1, measured"* has nothing that records Week 1.

> **A trap for the next reader.** `kpi_daily_rollup` **already exists** (migration `p11t09_kpi_rollup`, refreshed hourly by `core/arq_jobs.kpi_rollup_refresh`). It is **not** this. It is a materialised view over `execution_runs` giving runs/cost/tokens per (day, company, tag) — *platform operations* telemetry, recomputable from source at any time. The ten C6 KPIs are *business* measurements over tenant records, and once the underlying record changes the past value is **gone**. That difference is the entire reason one of these can be a view and the other must be a snapshot table.

## 2. What already exists, and what it is missing

| Piece | Shipped | The gap LEARN fills |
|---|---|---|
| Event store | `signals` — company-scoped, typed, deduped, replayable | No `learning.*` types; nothing writes learning events |
| Distilled learning | CORTEX Intelligence trees + `rule_lifecycle.py` (`candidate → confirmed → retired`, `filter_for_prompt`) | Rules are written by dreaming only; no outcome-driven proposal path |
| In-tenant learned aggregates | `SourceTrustScore` (`orm/trust.py`) + `memory/trust_learning.py` — Beta-posterior over source reliability | This is the **model** for a learning aggregate: counters, no content. Nothing generalises it |
| Routing observations | `routing_decisions` — per-decision, **company-scoped**, with a `signals` JSONB | Nothing aggregates it; the router still scores off *declared* capability only |
| KPI computation | `kpi/compute.py` — honest-absence rule, 10 definitions | Computes only "now". No persistence, no series, no trend |
| Autonomy response | `governance/demotion.py` + the 01:40 UTC sweep (C4) | Acts on triggers, but has no behavioural **baseline** to detect drift against |
| Per-user preference | *nothing* — grep finds no preference or density store anywhere | The whole store |

Two observations shape the design. First, **the tenant-scoped half of B10 is almost built**: `signals` is a company-scoped event store and the Intelligence tree is a company-scoped distillation store with a lifecycle. That is what makes decision 3 (reuse) reasonable. Second, **the pooled half has nowhere to live at all** — `signals.company_id` is `nullable=False` with an FK to `companies`, so a pooled record cannot be a signal without inventing a sentinel company, which is precisely the "NULL column enforced by discipline" pattern the overview rules out.

## 3. Decisions

Locked in the [charter](./00_charter.md) (2, 3, 8) and with Rahul on 2026-07-25 (KPI cadence). Not re-litigated here — recorded with what each obliges.

1. **B10 = SPLIT, at schema level.** Platform-level learning (routing, model performance — no business content) pools; tenant-level learning (charter tuning, density, behaviour) stays private. The pooled path must be **structurally incapable** of carrying tenant content. → §4.
2. **Learning store = REUSE** the signal bus + CORTEX Intelligence trees. No dedicated `learning_signals` table. → §5.
3. **Pooled learning is disclosed, with no opt-out** — justified *only* by decision 1's guarantee holding. → §4.4.
4. **KPI history = daily snapshot, every non-deleted company** (Rahul, 2026-07-25), chosen over activity-gated or weekly. Gaps make "Week 12 vs Week 1" ragged and a dormant-then-active tenant would have no baseline; weekly gives 12 points by Week 12, too coarse to see a regression land. → §6.

## 4. The B10 split, made structural

### 4.1 Why "pooled" cannot be a query convention

The tempting implementation is: keep writing `routing_decisions` (which has `company_id`), and have the router read `SELECT ... GROUP BY model, task_type` with no company filter. It would work, and it would be wrong for the reason the overview states — the guarantee would be a habit. One `WHERE company_id = :x` added by a well-meaning future author turns platform learning into per-tenant learning; one `SELECT *` in a debug endpoint exposes the tenant column that was only *conventionally* unused.

### 4.2 The pooled record has no company column and no free text

**`platform_observations`** (control-plane, new):

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `metric` | String(32) | closed vocabulary: `route_outcome` · `model_failure` · `fallback_used` · `admission_score` |
| `model_registry_id` | UUID FK → `model_registry`, nullable | a **platform** catalog row, never a tenant row |
| `task_type` | String(64) | from the shipped task-type vocabulary |
| `reason` | String(16) | the `routing_decisions` reason: `pinned`/`rule`/`auto`/`fallback`/`downshift` |
| `bucket_day` | Date | UTC day |
| `observations` | Integer | |
| `successes` | Float | |
| `latency_ms_sum` | BigInteger | |
| `cost_usd_sum` | Numeric(18,6) | |
| `contributor_floor_met` | Boolean | see §4.3 |
| `updated_at` | DateTime | |

Unique on `(metric, model_registry_id, task_type, reason, bucket_day)`.

**Every column is a FK to a platform catalog row, a member of a closed vocabulary, a date bucket, or a counter.** There is no `company_id`, no `payload`, no `text`, no JSON. A customer's name has nowhere to go — putting one there is a type error, not a policy violation. That is the whole of decision 1, and it is the property to defend in review: **adding a JSONB column to this table would silently repeal the guarantee decision 3 depends on.** A test asserts the column set is exactly this list.

### 4.3 Aggregate on write — in a job that can still see the tenant, writing a row that cannot

The pooled rows are produced by a **daily platform job** (`learning/pooling.py`, arq ~02:10 UTC) that reads `routing_decisions` for the day, groups by `(task_type, model_registry_id, reason)`, and upserts one bucket per group. The job is the only writer.

Inside the job, `company_id` is still visible — and that is deliberately where the **k-anonymity floor** is applied: a group whose rows come from fewer than `LEARN_POOL_MIN_CONTRIBUTORS` (default **3**) distinct companies is **dropped, not deferred**. Without it, a bucket for a model only one tenant has opted into (Kimi, say) is attributable to that tenant by anyone who can read the opt-in list. The floor is checked where the company ids are, and the row that survives has no company ids in it.

Two consequences worth stating plainly: pooled learning **lags a day** (fine — router priors are not a real-time input), and the platform learns nothing about rare configurations (correct — that is what the floor is *for*, and a rare configuration's small sample would not be worth learning from anyway).

### 4.4 What the pooled data is allowed to do

`platform_observations` feeds exactly one consumer: RTR v2's scoring (`intelligence/scoring.py`), which today scores a model on its **declared** `capability_profile`. LEARN turns the declaration into a prior that observation can correct — a model advertising `tool_reliability: 0.9` that fails tool calls a third of the time gets marked down.

Two limits, both load-bearing:

* **The correction is bounded** (±0.2 on a 0–1 axis, `LEARN_OBSERVATION_WEIGHT`). A bad week must not be able to invert the ordering; a genuinely bad model gets removed by EVX, not by drift in a score.
* **It can never flip a model's status.** `RegistryService.activate` stays the only path to `active` and it still refuses on a failed admission (EVX, Inc 5). Learning adjusts *preference among admitted models*; admission remains a gate that a preference cannot open.

Decision 3's disclosure obligation lands in [`increment-5/03a_data_flow_disclosure.md`](../increment-5/03a_data_flow_disclosure.md), extended with a section naming exactly these columns. **Decision 1 and decision 3 stand or fall together:** if the column set above cannot be held, the no-opt-out justification collapses and the question reopens. That is the first thing T1 finds out.

## 5. Tenant learning — reuse, with a lifecycle it already has

No new store. A tenant learning event is a **signal**; a distilled tenant learning is an **Intelligence-tree rule**.

**New signal types** (`signals/models.py::SignalTypes`), all company-scoped by the existing NOT NULL:

| Type | Emitted when | Consumed by |
|---|---|---|
| `learning.outcome_observed` | a run finishes with a gradeable outcome (CSAT, approval accepted/rejected, HITL override) | the distillation job |
| `learning.charter_tuning_proposed` | distillation produces a candidate change to an entity's `goal`/instructions | **SEGA** ([02](./02_sega.md)) |
| `learning.drift_detected` | a behavioural series steps off its baseline (§8) | C4's demotion sweep, Pragya stage 9 |
| `learning.density_observed` | a user repeatedly collapses/expands a surface | the preference store (§9) |

**Distillation** writes a `candidate` rule into the company's Intelligence tree and lets the shipped `rule_lifecycle.next_state` promote it on corroboration. This is why decision 3 is cheap: candidate→confirmed→retired, `filter_for_prompt`, and the `confirmed_only` gate are all built and tested. LEARN adds *a second producer of candidates* (outcomes) beside the existing one (dreaming) — it does not add a lifecycle.

**The seam with SEGA, confirmed** (the charter's carried-over question): **LEARN proposes, SEGA disposes.** LEARN may write a candidate rule and emit `learning.charter_tuning_proposed`; it may **never** mutate a `HierarchicalEntity`. Every entity mutation goes through SEGA's ledger, canary and blast-radius limits. The import boundary is enforced the way `pragya/acting.py`'s is — a test asserts `ai/learning/` does not import the entity service.

## 6. KPI history (VG-12)

### 6.1 `kpi_snapshots`

Control-plane, one row per (company, KPI, day):

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `company_id` | UUID FK → `companies` | tenant-scoped, per decision 1 |
| `kpi_key` | String(64) | one of the ten `KPI_DEFINITIONS` keys |
| `captured_on` | Date | UTC day |
| `value` | Numeric(18,6), **nullable** | NULL means *not measurable*. It never means zero |
| `measurable` | Boolean | the explicit flag, so a query never has to infer it from NULL |
| `missing` | JSONB | what was absent, copied from `KpiResult.missing` |
| `baseline_value` | Numeric(18,6), nullable | |
| `sample_size` | Integer | |
| `window_days` | Integer | |
| `unit` | String(16) | denormalised: a definition's unit may change, an old row's must not |

Unique on `(company_id, kpi_key, captured_on)` — the job is idempotent and a re-run overwrites the day it is re-running.

### 6.2 The honest-absence rule survives persistence

`compute.py` already refuses to return a number it cannot justify. Persisting that refusal is the interesting part: **a row recording "not measurable, missing `Invoice.due_date`" is history too.** It is what lets a Week-12 answer say *"this became measurable in Week 5, and here is the series since"* rather than showing a chart that silently starts in the middle. So the snapshot job writes a row for every (company, KPI) pair every day, measurable or not — never skipping the unmeasurable ones.

### 6.3 The job

`learning/kpi_snapshot.py`, arq daily at **01:25 UTC** — after the dunning sweep (01:10), before the demotion sweep (01:40), all within the established quiet hour. For every non-deleted company: `compute_all()`, then upsert ten rows.

* **Scope**: all non-deleted companies, including suspended and read-only ones. A tenant's KPI series should not acquire a hole because of a billing state — the series is *evidence about the business*, and C5's ladder is about payment.
* **Cost**: pure SQL against the tenant plane and the control plane; **no LLM tokens, so no `CostAttribution`**. It does add ~10 queries/tenant/day to the idle floor and belongs as a line in [`increment-2/05a_idle_cost_model.md`](../increment-2/05a_idle_cost_model.md) (E1) rather than in a budget envelope.
* **Retention**: keep daily rows for **400 days** (10 KPIs × 365 ≈ 3,650 rows/tenant/year — small enough that a rollup would be premature optimisation). A reaper past 400 days ships with the job, because a store with no reaper is an unbounded archive (the same lesson `voice_deferred_reap` records).
* **Backfill is impossible and the doc says so.** There is no honest way to reconstruct last month's open pipeline from records that have since changed. The first snapshot is day one of the series, which is the entire argument for LEARN going first.

### 6.4 Reading it

`GET /ai/kpi/history?keys=&from=&to=` beside the shipped `/ai/kpi/{definitions,business}` — one read path serving Pragya's stage 9, TWIN's forecast engine, STRAT's mandate reviews and (in Inc 7) the plinth trends and Seasons timeline. Four consumers, one endpoint, so "what was this KPI in week 3" has exactly one answer.

## 7. Reward hacking — the Karuna floor wins, structurally

B10 asks which wins when a KPI and the empathy floor disagree. The answer must not be a policy sentence, because a policy sentence is a thing a learning loop can optimise around. Three mechanisms:

1. **KPIs are never an agent objective.** The ten KPIs are *reported* (Pragya, dashboards) and never enter an entity's `goal`, prompt, or reward. An agent optimises task success as judged by its critics; nothing in the loop reads `collections_recovered` and asks for more of it. A test asserts no KPI key appears in any prompt-assembly path.
2. **Karuna bounds are constraints, not preferences.** A tuning proposal that would alter a governance band, widen an authority category, relax a consent/DNC check, or change a Karuna gateway's profile is **refused at proposal time** — it never becomes a candidate rule, so it never reaches a reviewer who might approve it while tired. Refusal at proposal beats refusal at review because it cannot be worn down.
3. **Proposals are scoped to what they can touch.** A `learning.charter_tuning_proposed` payload names an entity and a field from an allow-list (`goal`, `description`, Intelligence-tree rules). `governance`, `capabilities` and `logic_gate` are not on it.

Mechanism 2 is the one to mutation-test: remove the refusal, and a fixture proposing an autonomy widening must fail — and only that test.

## 8. Drift detection

Drift is *behaviour changing without anyone deciding it should*. LEARN records the series; the shipped C4 machinery reacts.

Per (company, entity), weekly: HITL approval rate, rejection rate, escalation rate, consent-refusal rate, mean steps per run, and `csat_score` mean where present. All are counts and ratios over `execution_runs`/`human_approvals` — **no content**. Stored as tenant-scoped rows (`entity_behaviour_weekly`), because this is per-tenant learning by decision 1.

A step change beyond `LEARN_DRIFT_SIGMA` (default 2.5) against the entity's own trailing baseline emits `learning.drift_detected`. It does **not** demote — `governance/demotion.py` owns demotion and already has triggers and an anti-rubber-stamp promotion rule; LEARN gives it one more trigger rather than a second opinion. Two demotion authorities would be exactly the "which store is this row in" confusion the overview warns about, in the enforcement layer.

## 9. The preference / density store

Nothing exists today. Small and deliberately dull:

`user_preferences` — `(user_id FK, company_id FK, key String(64), value JSONB, updated_at)`, unique `(user_id, key)`. Tenant-scoped. Keys are namespaced (`density.surface.<name>`, `notify.<channel>`).

Explicit preferences are written by the user. *Learned* density is a `learning.density_observed` signal that proposes a change; the applied value is written only when a threshold is crossed, and the surface always shows the user what was learned. Vihara (Inc 7) is the consumer; Inc 6 ships the store and the signal so the observation series starts accumulating now, for the same reason KPI history does.

## 10. Data model summary

| Table | Plane | Scope | Migration |
|---|---|---|---|
| `platform_observations` | control | **none** (no company column) | `learn001` |
| `kpi_snapshots` | control | company | `learn001` |
| `entity_behaviour_weekly` | control | company + entity | `learn001` |
| `user_preferences` | control | user + company | `learn001` |

One migration off `fleet001`, four tables, no tenant-schema changes. New package **`ai/learning/`** — must be added to `CLEAN_PACKAGES` in `scripts/typecheck_ai.py` or it escapes strict typing.

## 11. Task plan

| # | Task | Gate |
|---|---|---|
| **T1** ✅ | **The B10 guarantee, first.** `learning/models.py` + `learn001`. Assert the `platform_observations` column set is exactly §4.2; assert no FK to `companies`. **If this cannot hold, stop and reopen decision 3** (§4.4) | unit + `*_db` |
| **T2** ✅ | `learning/pooling.py` — the daily aggregation job with the k-anonymity floor; ~~upsert semantics~~ **replace-the-day** (§14.2); drop (never defer) below-floor groups | unit (pure grouping) + `*_db` |
| **T3** ✅ | `learning/kpi_snapshot.py` + the reaper + the arq 01:25 cron; unmeasurable KPIs snapshot as absence | `*_db`, incl. a re-run idempotency test |
| **T4** | `GET /ai/kpi/history` | router test |
| **T5** | The four `learning.*` signal types + `learning/outcomes.py` (observation → candidate rule via the shipped lifecycle) | unit + `*_db` |
| **T6** | Charter-tuning proposals + the §7 refusals + the LEARN⇸SEGA import boundary test | unit, **mutation-tested** |
| **T7** | `learning/drift.py` — the weekly behaviour series + `learning.drift_detected`, wired as a C4 trigger | unit + `*_db` |
| **T8** | `user_preferences` + get/set API + `learning.density_observed` | router + `*_db` |
| **T9** | Bounded observation correction in `intelligence/scoring.py`; **parity/eval must stay 16 green** | parity/eval + unit |
| **T10** | Extend [03a_data_flow_disclosure.md](../increment-5/03a_data_flow_disclosure.md) to name the pooled columns (decision 3's obligation) | doc |

T9 is where the billing canary bites: it touches the routing path, and the HANDOFF §5 rule is that unit tests stay green while every agent run fails. Run `pytest tests/parity tests/eval` before believing it.

## 12. Honest risks

| Risk | Why it is real |
|---|---|
| **The k-anonymity floor may starve the pooled data** | A platform with few tenants per (model, task) combination writes almost nothing. Mitigation is patience, not a lower floor — and the router works today without it |
| **Decision 1 and 3 are coupled** | §4.4. If T1 fails, the no-opt-out posture reopens, and it is better to learn that in T1 than after the disclosure is published |
| **Two candidate producers into one tree** | Dreaming and outcomes both write candidates. If they disagree, `rule_lifecycle` resolves by corroboration, which is the right answer — but the tree's provenance field must distinguish them or a future debugger cannot tell which loop taught the agent something |
| **KPI history cannot be recovered** | Every week LEARN slips is a week no later effort can supply |
| **`kpi_daily_rollup` will be mistaken for this** | Named in §1 for exactly that reason |

## 13. Brainstorm decisions

*(Answered — do not re-litigate.)*

1. **Pooled vs private:** split, structural (charter 2).
2. **Store shape:** reuse bus + CORTEX for tenant learning; a narrow, company-less aggregate for the pooled path — which is not the `learning_signals` table decision 3 rejected, but its opposite: an aggregate with no event content (§4.2).
3. **Opt-out:** none, disclosed (charter 8), conditional on §4.2 holding.
4. **KPI cadence:** daily, all non-deleted companies (Rahul, 2026-07-25).
5. **Who mutates entities:** SEGA only. LEARN proposes (§5).
6. **KPI vs Karuna:** the floor wins, by never letting KPIs into an objective (§7).

---

## 14. Build notes (2026-07-25, branch `inc6/learn`)

### 14.1 T1 — the schema guarantee

**The guarantee holds.** §4.4's stop-or-go passed: the pooled path can be made structurally incapable of carrying tenant content without contorting anything, so charter decisions 2 and 8 both stand and the increment proceeds as designed.

**What was built.** `ai/learning/` (added to `CLEAN_PACKAGES`) with `models.py` — `PlatformObservation`, `KpiSnapshot`, `EntityBehaviourWeekly`, `UserPreference` — plus migration **`learn001`** off `fleet001` (the new head) and registration in `migrations/env.py`. Import-light throughout (column FKs, no `relationship()`), following the `intelligence/models.py` precedent, so a test touching only these tables need not register the auth/execution mapper graph.

**Three design deltas.**

1. **The grain needed an expression index, not a unique constraint.** `model_registry_id` is nullable — `routing_decisions`' is, because an un-bound legacy integration still routes — and **Postgres treats NULLs as distinct in a unique constraint**. A plain `UniqueConstraint` would therefore have permitted an unbounded number of identical *"no model"* buckets, and T2's daily upsert would have appended forever for exactly the rows most likely to exist early. The grain is now a unique index over `coalesce(model_registry_id, <nil uuid>)`. Chosen over PG15's `NULLS NOT DISTINCT` so the schema carries no version floor. **The `*_db` test found this**, which is the argument for writing the database-level assertions rather than trusting the metadata ones.
2. **`POOLED_COLUMNS` lives in the model module, not only in the test.** A reader adding a column should meet the constraint in the file they are editing; a test three directories away is a discovery made after the fact.
3. **The metadata tests read `fk.target_fullname`, not `fk.column`.** Resolving the `Column` requires the referenced table to be in the same metadata, which import-lightness deliberately prevents. The declared string is the right thing to assert anyway — it is what the DDL emits.

**The guarantee is mutation-tested.** Adding `company_id` + a `notes` JSONB to `PlatformObservation` failed exactly four tests — no-company-column, no-tenant-FK, exact-column-set, no-free-form-column — and left the tenant-path and KPI tests green. A guarantee no test has been observed to enforce is a comment.

**Verification.** typecheck **262 files** strict · layout lint · **1570 unit** (+16) · **16 parity/eval** · **296 integration** (+8) · `learn001` applies, downgrades and re-applies; head is `learn001`.

~~**Honest limit:** these are stores with no writers yet.~~ — closed by T2 and T3 below.

### 14.2 T2 — the pooling job and its floor

`learning/pooling.py`: a pure `bucket_decisions(rows, min_contributors=)` doing the grouping and the floor, and a thin `pool_day(db, day)` around it. `LEARN_POOL_MIN_CONTRIBUTORS` defaults to **3**. Cron `platform_pooling_sweep` at **02:10 UTC**, over *yesterday* — a day cannot be aggregated until it is over.

**Three deltas.**

1. **Replace the day, don't upsert it.** The design said upsert; the job recomputes the whole day from source, so deleting the day's rows and re-inserting is both simpler and more obviously idempotent. It also avoids depending on `ON CONFLICT` inference against the grain's *expression* index (`coalesce(model_registry_id, …)`), which is a fragile thing for a cron to rest on.
2. **`contributors` is computed and deliberately not stored.** The `Bucket` dataclass carries it so a caller can assert the floor was applied, but the table records only `contributor_floor_met` — a distinct-company count is itself a small fact about tenants, and the point of this table is that it holds none.
3. **The success proxy is inherited, limitations included.** `successes` = decisions that did not fall back, the same SLO proxy `intelligence/canary.py` uses, and it carries the same weakness: shipped telemetry does not attribute a *generate* failure to a model, so a model that fails loudly and one that fails silently look alike here. Named in the module docstring rather than discovered later.

**The floor is mutation-tested.** Removing the `contributors < min_contributors` check failed exactly six tests — all of them floor tests, including `test_one_tenant_with_many_rows_never_clears_the_floor` — and left the grouping and counting tests green. That test is the load-bearing one: the floor counts **distinct companies, not rows**, because a floor a single chatty tenant can clear protects nobody while looking like it protects everybody.

### 14.3 T3 — the job that starts the clock

`learning/kpi_snapshot.py` (`snapshot_company` / `snapshot_all` / `reap_old_snapshots`), cron `kpi_snapshot_sweep` at **01:25 UTC** — after C5's dunning sweep (01:10), so a reading reflects the billing state just entered, and before C4's demotion sweep (01:40), so a demotion decided at 01:40 belongs to tomorrow's series.

**Four deltas.**

1. **Scope is `type = 'TENANT'`, not "all non-deleted companies".** `companies` has **no `deleted_at` column** — the design's phrase assumed one. APP and PARTNER rows are not businesses with an open pipeline or an invoice ledger. Suspended and read-only tenants *are* included, as designed: a KPI series should not acquire a hole because of a billing state.
2. **"A new tenant is ten absences" was too strong, and the test caught it.** `agent_hitl_load` has no record prerequisites — it counts pending approvals — so **zero waiting approvals is a genuine measurement on day one**, not an absence. §6.2's rule is unchanged (a row is written for every KPI every day, measurable or not); what changed is the assertion, which now pins the *correspondence* — `value IS NULL` exactly when `measurable` is false, and every absence names what is missing — plus a guard that no other KPI quietly becomes "measurable at zero" for an empty tenant.
3. **One tenant's failure must not cost every tenant a day.** `snapshot_all` catches per-company, rolls back, logs and continues, returning the failed ids. Days of history are the one thing this workstream cannot get back, so a single tenant mid-provision must not take the rest of the estate down with it.
4. **The reaper runs inside the same cron.** A reaper on its own schedule is a reaper that eventually stops being deployed. `LEARN_KPI_RETENTION_DAYS` defaults to 400.

**One typing note:** SQLAlchemy's async `Result` is typed without `rowcount`, so the reaper counts via `DELETE … RETURNING id`. Worth knowing before the next `DELETE`-shaped job — it type-checks fine through `func`-style access and fails under `--strict` here.

### 14.4 Verification (T1–T3)

typecheck **265 files** strict · layout lint · **1584 unit** (+30) · **16 parity/eval** · **305 integration** (+17) · migration head `learn001`, applies/downgrades/re-applies.

**Honest limit:** both jobs are wired to arq crons but have **never run on a live schedule** — they are exercised by tests that call them directly. And the KPI series genuinely starts the day this deploys; there is no backfill, by construction.

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-25 | v1.2 — **T2 + T3 built** (§14.2–§14.4). Pooling replaces the day rather than upserting it; the floor is mutation-tested and counts distinct companies, not rows. The snapshot job's scope corrected to `type='TENANT'` (`companies` has no `deleted_at`), and the "a new tenant is all absences" claim corrected — `agent_hitl_load` is genuinely measurable at zero on day one. |
| 2026-07-25 | v1.1 — **T1 built** (§14). The B10 stop-or-go passed. One real defect found by the DB-level test: the pooled grain needed a `coalesce` expression index because Postgres treats NULLs as distinct in a unique constraint. |
| 2026-07-25 | v1.0 — design written. B10 split into its three real questions; the pooled record shaped so tenant content cannot fit; k-anonymity applied in the job rather than the table; `kpi_snapshots` with the honest-absence rule persisted; the LEARN⇸SEGA seam confirmed (propose vs dispose); reward hacking answered structurally; drift feeding C4 rather than duplicating it. |
