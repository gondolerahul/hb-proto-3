# Increment 6 / TWIN — The Glasshouse (closes VG-09)

> **Status:** v1.1 — design locked (§3). **T1 BUILT 2026-07-25** (branch `inc6/twin`) — the plane prototype holds; see §14. T2–T11 open.
> **Closes:** gap-analysis **VG-09** (the Glasshouse has no backend — the largest single gap). Consumes **VG-10**'s canary from SEGA rather than building a second one.
> **Depends on:** LEARN ([01](./01_learn.md)) — the forecast engine reads `kpi_snapshots` · SEGA ([02](./02_sega.md)) — the promotion pipeline **calls** SEGA's entity canary and version ledger · `tenant_schema/data_plane.py` · the PolicyGate · `inward_auth/guard.py` (certified approval).
> **Feeds:** STRAT ([04](./04_strat.md)) — mandate reviews read honesty grades · Vihara G5 (Increment 7).
> **Parent:** [00_overview.md](./00_overview.md) · [00_charter.md](./00_charter.md) decisions 4 and 7 · ratified spec [§6.4, L5, L6](../genui_design_gate_spec.md).

---

## 1. What this is

> *"Beside the real, there is a glass room."* — Binding Law 3.

The Glasshouse is where a consequential change is **tried before it is bet on**: take an idea — a charter edit, a new agent, a policy change, a pricing move — run it against the business's own history in an isolated plane, and get back a result that states how much it should be believed.

Nothing simulation-shaped exists anywhere in `src/ai/` today. This is the largest single net-new subsystem in the increment, and it has no precedent in the codebase to copy.

**One thing it is not.** `POST /ai/signals/{id}/replay` (`signals/api.py`) already exists and replays a signal into the **live** plane. It is an operational retry, not a twin. A future reader will find it and think the replay engine is built; §4 exists partly to make that impossible.

## 2. The four hard parts

| Part | Why it is hard |
|---|---|
| **The plane** | An isolated copy of a tenant's business data that is cheap to make and impossible to write back from by accident |
| **Honesty** | A grade that cannot be softened — including by the code that produces it |
| **Cost** | Decision 7 made twin spend tenant-initiated, so every what-if is visibly the tenant's money (§6) |
| **Promotion** | Getting a good result out of the glass room and into reality without inventing a second canary |

## 3. Decisions

1. **The twin plane is a second schema, not a third backend** (§4). `data_plane.py`'s two backends stay two.
2. **Twin spend is TENANT-initiated** (charter decision 7, overriding ratified spec §12.1). `CostAttribution.TWIN_RUN` stays **out** of `PLATFORM_INITIATED_ATTRIBUTIONS`. The consequence — a Glasshouse that visibly costs money is one people use less — is answered by §6, not by re-arguing the class.
3. **The grade is computed, never supplied.** No API accepts a grade as input (§5).
4. **Certified actions are simulated by substitution, not by a flag** (§7) — L5.
5. **TWIN owns no canary.** Promotion calls SEGA's (§8) — [00_overview](./00_overview.md) §3.
6. **Simulated people are permitted** (owner decision, concepts §6.4), disclosed as such, and reuse `persona_service.py`.

## 4. The twin data plane

### 4.1 A sibling schema

`schema_name_for(company_id)` returns `t_<hex>`. The twin is **`t_<hex>_tw`** — created by the same `bootstrap`, holding the same `TenantBase` tables, reached through the same `schema_translate_map` mechanism. On the container backend, where `tenant` maps to `None` (the dedicated DB's public schema), the twin maps to a named `twin` schema inside that same database.

```
TenantDataPlane.session(company_id, plane=Plane.LIVE | Plane.TWIN)
TenantDataPlane.ensure_ready(company_id, plane=...)
```

One parameter, both backends, no new infrastructure. The overview's risk row worried that "the two-backend design has never run a third mode" — this design means **it still doesn't**. The twin is a second *schema*, which both backends already know how to address.

**The isolation guarantee is the identifier.** A twin session can only ever resolve `tenant.*` to the twin schema; there is no session object that can see both planes, so a write cannot cross by accident. A test asserts that a twin session's `search_path`-equivalent resolution never yields the live schema, and that the record service, handed a twin session, writes only there.

### 4.2 Materialisation is bounded, not a copy of everything

Copying a tenant's whole business database per what-if is exactly the expense decision 7 makes visible. Instead a scenario declares a **scope** — which HBS objects, over what window — and materialisation copies:

* **always**: `tenant_entity_defs` (the schema itself) and the HBS spine, which are small;
* **in scope**: records of the named objects whose `updated_at` falls in the window;
* **never**: documents, chunks or embeddings. The twin **reads** the control-plane memory store; it does not copy or re-embed it. Re-embedding a tenant's library for a what-if would be the single most expensive thing the Glasshouse could do, and it would buy nothing — retrieval is not what the scenario is varying.

Materialisation is `INSERT … SELECT` between two schemas on the same database (schema backend) or the same DB (container backend) — no application round-trip.

### 4.3 Lifecycle

A twin plane is **per scenario run** and reaped on completion (rows dropped, schema kept and truncated for reuse). A permanent shadow of every tenant would double the storage bill of a feature most tenants use occasionally.

## 5. Honesty grading (L6)

### 5.1 The three grades mean three different things

| Grade | What it means | What produced it |
|---|---|---|
| `replay` | Real historical inputs, the real code path, isolated writes | The replay engine (§5.2) |
| `forecast` | A projection from a measured series, by a stated method, with an interval | The forecast engine (§5.3) |
| `unknown` | Neither — no history, no series, or a lever outside anything observed | Everything else |

### 5.2 What `replay` does *not* promise

**Replay is not determinism.** The same signal re-run through the same agent with the same model does not produce the same tokens, and any grade that implied it would be a lie the platform tells about itself. `replay` promises: *the inputs were real events that actually happened, the code path was the real one, and the writes went nowhere.* It does not promise the output would recur.

This is stated in the doc, in the module docstring, and in the grade's own description string that the surface renders. If it is only in the doc, the surface will eventually claim more than the engine can support.

### 5.3 Forecast

Over `kpi_snapshots` (LEARN, [01](./01_learn.md) §6). The method is declared with the result — a seasonal-naive or linear projection with a prediction interval — and a forecast is refused outright below `TWIN_MIN_SERIES_POINTS` (default 8 daily points) rather than returned with a wide interval nobody reads. **A forecast the day after LEARN ships is `unknown`, and it should be**: this is the coupling the overview names, made visible rather than papered over.

### 5.4 The grade is computed and monotone

```
grade(inputs) -> Grade          # pure, total
```

Two properties:

* **No API accepts a grade.** `TwinRun.grade` is written by the engine from what the run actually had. There is no override parameter, no admin setting, no "trust me" flag. L6 says the honesty layer is *never softened*; the cheapest way to guarantee that is to give no one a way to soften it.
* **A mixed result takes the worst grade of its inputs** — the same monotone discipline as SEGA's taint (§7 there). A comparison of a replayed scenario against a forecast baseline is a `forecast` result, not a `replay` one.

## 6. Keeping a what-if cheap

Decision 7's product consequence, answered concretely:

1. **Bounded windows.** Default replay window 7 days, hard cap `TWIN_MAX_WINDOW_DAYS` (30). The cap is a refusal, not a truncation — silently shrinking a window would make two runs incomparable without saying so.
2. **Cached baselines.** The incumbent's replay over a given (entity version, window, scope) is stored as a `TwinRun` with `is_baseline=True` and reused by every scenario comparing against it. Most Glasshouse sessions vary the candidate, not the baseline, so this halves the typical cost.
3. **No re-embedding** (§4.2).
4. **Estimate before spend.** `POST /ai/twin/scenarios/{id}/estimate` returns projected signal count and cost from the window and scope before anything runs; the run endpoint refuses without an acknowledged estimate. A tenant should never learn a what-if's price afterwards.
5. **Wallet holds apply.** Twin runs draw on the tenant envelope through the shipped hold mechanism — no special path, and the E3 race stays closed.
6. **A per-company daily twin budget** (`TWIN_DAILY_CAP_USD`) that parks rather than fails: the shelf shows "resumes tomorrow", the same posture platform work takes at its cap.

## 7. Certified actions: simulated, never executed (L5)

A twin run executes with a **substituted tool set**: every Karuna gateway, connector write-back and money tool is replaced by a recording stub that returns a plausible result and logs the call. Not a flag on the live executor — a different registry. A boolean like `dry_run=True` is one missing `if` away from sending a real invoice, and this is precisely the class of bug that must be impossible rather than tested-for.

**The PolicyGate still runs.** A simulated payout still raises the HITL card it would raise in reality, and the scenario result shows it. Half the value of rehearsing a change is learning what it would have asked permission for.

Consent and DNC checks also still run: a broadcast scenario that would have been refused by the consent registry must be refused in the glass room, or the rehearsal teaches the wrong lesson.

## 8. The promotion pipeline

Ratified spec §134: *diff → certified approval → Board build → canary → GA.*

| Stage | Who owns it |
|---|---|
| **Diff** | SEGA's `entity_versions` (two snapshots, §5 there) |
| **Certified approval** | `inward_auth/guard.py` — promoting a rehearsed change is T2, the same ceremony as an autonomy raise |
| **Board build** | The shipped Meta-Agent board (`ai/meta/board/`) |
| **Canary** | **SEGA's** `evolution/entity_canary.py` — TWIN calls it |
| **GA** | SEGA's promote path |

TWIN contributes the *evidence* (which scenario, which grade, which metrics) and carries it onto the approval card. It contributes no new gate: a Glasshouse result is an argument, never an authorisation.

## 9. The Scenario Shelf and tournaments

`twin_scenarios` is the shelf — named, re-runnable, owned by a user, listed for the tenant. A tournament compares N scenarios on one metric set.

The comparison view has one rule worth building in rather than styling in: **grades are compared, not averaged.** A tournament mixing a `replay` result with an `unknown` one shows both grades on the row and refuses to rank across them without the mismatch stated. Ranking a forecast above a replay because its number was bigger is the failure mode L6 exists to prevent.

## 10. Data model

| Table | Plane | Notes |
|---|---|---|
| `twin_scenarios` | control | company, name, `kind` (`charter` · `policy` · `roster` · `pricing` · `custom`), `levers` JSONB, `scope` JSONB (objects + window), `status`, `created_by` |
| `twin_runs` | control | scenario FK (nullable for baselines), `grade`, `method`, `metrics` JSONB, `cost_usd`, `is_baseline`, `entity_version_id` FK → `entity_versions`, `started_at`/`finished_at`, `refusal_reason` |

The twin *plane* is **not** a migration — tenant tables bootstrap per tenant (SCH, Inc 1; the Inc-4 `_sync_columns` precedent). Migration `twin001` off `sega001` adds the two control-plane tables and nothing else.

New package **`ai/twin/`** → `CLEAN_PACKAGES`. New attribution `CostAttribution.TWIN_RUN`, **not** in `PLATFORM_INITIATED_ATTRIBUTIONS` (decision 2) — and per the HANDOFF §5 rule, that classification is the deliverable, not the enum member.

New signal types: `twin.scenario_run`, `twin.promotion_proposed`.

## 11. Task plan

| # | Task | Gate |
|---|---|---|
| **T1** | **Prototype the plane first** ([00_overview](./00_overview.md) §7 says so). `Plane` enum + `session(company_id, plane=)` + twin bootstrap + the isolation test | `*_db` |
| **T2** | Bounded materialisation (`INSERT … SELECT`), scope + window, reaper | `*_db` |
| **T3** | `twin/models.py` + `twin001`; scenarios and runs | `*_db` |
| **T4** | `twin/grading.py` — pure, total, worst-of-inputs; **no input path accepts a grade** | unit, **mutation-tested** |
| **T5** | `twin/replay.py` — historical signals → twin plane at a chosen entity version | `*_db` |
| **T6** | `twin/substitution.py` — the stub tool registry; PolicyGate and consent still run | unit + `*_db`, **mutation-tested** (removing substitution must fail an "external call attempted" test) |
| **T7** | `twin/forecast.py` over `kpi_snapshots`; refuse below the series floor | unit |
| **T8** | Cost: `TWIN_RUN` attribution, estimate endpoint, wallet holds, daily cap → park. **`tests/parity` is the canary** | parity/eval + `*_db` |
| **T9** | `twin/api.py` — shelf CRUD, estimate, run, compare | router + `*_db` |
| **T10** | Promotion: diff + evidence → T2 certified approval → SEGA canary | `*_db` |
| **T11** | Simulated counterparties over `persona_service.py`, disclosed in the result | unit |

T1 before everything: if the sibling-schema approach does not hold, every later task changes shape, and that is worth knowing in week one.

## 12. Honest risks

| Risk | Why it is real |
|---|---|
| **No precedent in the codebase** | Nothing simulation-shaped exists. T1 is a prototype for that reason |
| **`replay` will be over-read** | Users will hear "replay" as "this is what would happen". §5.2 is a mitigation in three places, and it is still the most likely way this feature misleads someone |
| **Forecast is empty at launch** | It reads a series that starts the day LEARN ships. Correct, and it will look broken. The refusal message must say *why* it cannot forecast yet, not just that it cannot |
| **Substitution is the whole of L5** | One un-substituted tool is a real external effect from a rehearsal. T6's mutation test is the load-bearing one in this workstream |
| **Cost visibility may suppress usage** | Decision 7 accepted this trade deliberately; §6 mitigates but does not remove it. Worth measuring once Vihara ships the surface |

## 13. Brainstorm decisions

*(Answered — do not re-litigate.)*

1. **Third backend or second schema:** second schema (§4.1).
2. **Persistent twin or per-run:** per-run, reaped (§4.3).
3. **Grade authorship:** computed only (§5.4).
4. **Dry-run flag or substituted tools:** substitution (§7).
5. **Whose canary:** SEGA's (§8).
6. **Budget class:** tenant-initiated (charter 7).
7. **Simulated people:** permitted and disclosed (concepts §6.4).

---

## 14. Build notes — T1 (2026-07-25, branch `inc6/twin`)

**T1 is built. T2–T11 are not.** §11 says T1 goes first because "if the sibling-schema approach does not hold, every later task changes shape, and that is worth knowing in week one." **It holds**, and the risk row in [00_overview](./00_overview.md) §7 can be closed on that basis.

### 14.1 What shipped

`tenant_schema/data_plane.py`: a `Plane` enum threaded through `schema_name_for`, `ensure_ready`, `session` and `get_tenant_session`, defaulting to `LIVE` so all 46 existing call sites mean exactly what they always meant. Schema backend → `t_<hex>_tw`; container backend → a named `twin` schema inside the tenant's own database (the live plane there is the database's default schema and has no name to suffix). Plus `drop_twin` for §4.3's reaper. Tests: `tests/integration/test_twin_plane_db.py` (13).

**No migration, as designed** — tenant tables bootstrap per tenant.

### 14.2 Three build findings

1. **Readiness must be memoised per *plane*, not per tenant.** The shipped `_ready` set keyed on `company_id.hex`; leaving it that way would let a readied live plane make the twin *look* ready, handing back a session pointed at a schema with no tables in it. Keyed `"{hex}:{plane}"` now.

2. **The reaper drops the schema rather than truncating tables.** §4.3 says "rows dropped, schema kept and truncated for reuse". Truncating keeps `tenant_entity_defs` — so a scenario that varied the *schema* (which is exactly what a `charter` or `roster` scenario does) would leave that variation behind for the next run to inherit, silently. Dropping is the honest reset, and re-bootstrapping is cheap because the spine is small (§4.2 already says so).

3. **`schema_translate_map` does not touch textual SQL.** It rewrites SQLAlchemy constructs only, so a raw `SELECT ... FROM tenant.tenant_records` resolves against a literal schema named `tenant` and fails outright. Everything reaching the twin plane must go through the ORM models. This is a constraint on **every later TWIN task** — T2's materialisation in particular, which §4.2 specifies as `INSERT … SELECT` between two schemas and will therefore have to build those statements with real schema names rather than the symbolic token.

### 14.3 What the isolation test actually asserts

Both directions (a twin write is invisible to live; a live write is invisible to the twin), the translate map carries exactly one mapping and it is the twin's, a reaped twin carries nothing over — and, the one that matters, **the real `RecordService` writes only where it was handed**. Isolated plumbing underneath a service that resolves its own schema would be no guarantee at all, so the guarantee is tested through the thing that will actually do the writing.

### 14.4 Gates

typecheck **289** files strict · layout lint · **1847 unit** · **404 integration** (+13).

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-25 | v1.1 — **T1 BUILT.** §14 added: the sibling-schema prototype holds on both backends, so the overview's "no precedent in the codebase" risk is answered. Three build findings — readiness memoised per plane; the reaper drops rather than truncates (a schema-varying scenario would otherwise be inherited); and `schema_translate_map` not applying to textual SQL, which constrains T2's materialisation. |
| 2026-07-25 | v1.0 — design written. The twin plane resolved as a sibling schema rather than a third data-plane backend, so both shipped backends host it unchanged; materialisation bounded and explicitly excluding embeddings; honesty grading made computed-only and monotone, with `replay ≠ determinism` stated where it cannot be missed; certified-action safety by tool substitution rather than a dry-run flag; the promotion pipeline delegated to SEGA's canary; six concrete answers to decision 7's cost consequence. |
